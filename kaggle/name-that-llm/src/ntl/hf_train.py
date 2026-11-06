"""Transformer track: same folds, same OOF format, so `ntl.failure` and R work unchanged.

    python -m ntl.hf_train --data data/raw --model microsoft/deberta-v3-small --out artifacts/deberta
    python -m ntl.hf_train --data data/raw --model /kaggle/input/some-llm --lora-r 16 --save-models

Needs a GPU to be useful, and a model snapshot attached as a Kaggle dataset for offline runs.
Fold models are saved only with --save-models; weights stay out of git. Test is hidden until the
scoring rerun, so test predictions come from `predict_folds`, inside the submission kernel.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch.nn.functional import cross_entropy
from torch.utils.data import DataLoader
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from .data import ID, LABEL, PROMPT, TEXT, load
from .metrics import balanced_accuracy
from .splits import grouped_folds


def batches(tokenizer, texts: list[str], labels, bs: int, max_length: int, shuffle: bool):
    """Pad per batch, not to the longest passage overall. On CPU that saves a lot of time."""
    enc = tokenizer(list(texts), truncation=True, max_length=max_length)
    rows = [{k: v[i] for k, v in enc.items()} for i in range(len(texts))]

    def collate(picked: list[int]):
        batch = dict(tokenizer.pad([rows[i] for i in picked], padding=True, return_tensors="pt"))
        return (batch, torch.as_tensor(labels[picked]) if labels is not None else None)

    return DataLoader(range(len(rows)), batch_size=bs, shuffle=shuffle, collate_fn=collate)


def train_one(model, tokenizer, tr_texts, tr_y, va_texts, args, device) -> np.ndarray:
    loader = batches(tokenizer, tr_texts, np.asarray(tr_y), args.batch_size, args.max_length, True)
    trainable = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(trainable, lr=args.lr, weight_decay=0.01)
    accum = getattr(args, "grad_accum", 1)
    steps = max(1, len(loader) * args.epochs // accum)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=args.lr, total_steps=steps)
    model.to(device).train()
    amp = device == "cuda"
    for _ in range(args.epochs):
        for i, (batch, y) in enumerate(loader, 1):
            batch = {k: x.to(device) for k, x in batch.items()}
            with torch.autocast("cuda", dtype=torch.bfloat16, enabled=amp):
                loss = cross_entropy(model(**batch).logits, y.to(device),
                                     label_smoothing=args.label_smoothing) / accum
            loss.backward()
            if i % accum == 0 and sched.last_epoch < steps:
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step()
                opt.zero_grad()
                sched.step()
    return predict(model, tokenizer, va_texts, args, device)


@torch.no_grad()
def predict(model, tokenizer, texts, args, device) -> np.ndarray:
    model.to(device).eval()
    order = np.argsort([len(t) for t in texts])  # similar lengths together, less padding
    sorted_texts = [texts[i] for i in order]
    loader = batches(tokenizer, sorted_texts, None, args.batch_size * 2, args.max_length, False)
    out = [torch.softmax(model(**{k: x.to(device) for k, x in batch.items()}).logits, -1).cpu()
           for batch, _ in loader]
    proba = torch.cat(out).numpy()
    restored = np.empty_like(proba)
    restored[order] = proba
    return restored


def with_lora(model, r: int):
    """Train a small adapter and the head instead of the whole model. Public reports credit this
    kind of fine-tune with most of the gap over classical models, so it is the first GPU experiment."""
    from peft import LoraConfig, TaskType, get_peft_model

    config = LoraConfig(task_type=TaskType.SEQ_CLS, r=r, lora_alpha=2 * r, lora_dropout=0.05,
                        target_modules="all-linear")
    return get_peft_model(model, config)


def build_model(path: str, n_labels: int, lora_r: int = 0):
    model = AutoModelForSequenceClassification.from_pretrained(path, num_labels=n_labels)
    if model.config.pad_token_id is None:
        model.config.pad_token_id = model.config.eos_token_id
    return with_lora(model, lora_r) if lora_r else model


def load_tokenizer(path: str):
    tokenizer = AutoTokenizer.from_pretrained(path)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    return tokenizer


def save_classes(out: str | Path, classes) -> None:
    Path(out).mkdir(parents=True, exist_ok=True)
    (Path(out) / "classes.json").write_text(json.dumps([str(c) for c in classes]))


def predict_folds(folds_dir: str | Path, base: str, texts: list[str], args, device: str,
                  tokenizer=None) -> tuple[np.ndarray, list[str]]:
    """Mean probability over saved fold models, in the order given by classes.json.

    A folder with `adapter_config.json` is a LoRA adapter on `base`. Any other is a full model.
    """
    folds_dir = Path(folds_dir)
    classes = json.loads((folds_dir / "classes.json").read_text())
    tokenizer = tokenizer or load_tokenizer(base)
    total, fold_dirs = 0.0, sorted(folds_dir.glob("fold*"))
    if not fold_dirs:
        raise FileNotFoundError(f"no fold* folders in {folds_dir}")
    for fold in fold_dirs:
        if (fold / "adapter_config.json").exists():
            from peft import PeftModel

            model = PeftModel.from_pretrained(build_model(base, len(classes)), fold)
        else:
            model = AutoModelForSequenceClassification.from_pretrained(fold)
        total = total + predict(model, tokenizer, texts, args, device)
        del model
    return total / len(fold_dirs), classes


def run(train: pd.DataFrame, args, build_model, tokenizer, device) -> tuple[np.ndarray, np.ndarray]:
    classes = np.array(sorted(train[LABEL].unique()))
    y = np.searchsorted(classes, train[LABEL].to_numpy())
    folds = grouped_folds(train, args.folds, args.seed)
    if args.save_models:
        save_classes(args.out, classes)
    proba = np.zeros((len(train), len(classes)))
    for k in range(args.folds):
        fit, val = folds != k, folds == k
        model = build_model(len(classes))
        proba[val] = train_one(model, tokenizer, train.loc[fit, TEXT].tolist(), y[fit],
                               train.loc[val, TEXT].tolist(), args, device)
        score = balanced_accuracy(y[val], proba[val].argmax(axis=1))
        print(f"fold {k}: balanced accuracy {score:.4f}", flush=True)
        if args.save_models:
            model.save_pretrained(Path(args.out) / f"fold{k}")
    return proba, folds


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default=None)
    ap.add_argument("--model", default="microsoft/deberta-v3-small")
    ap.add_argument("--out", default="artifacts/hf")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--max-length", type=int, default=384)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--label-smoothing", type=float, default=0.05)
    ap.add_argument("--save-models", action="store_true")
    ap.add_argument("--lora-r", type=int, default=0, help="LoRA rank; 0 trains the whole model")
    ap.add_argument("--grad-accum", type=int, default=1)
    return ap


def write_oof(train, proba, folds, out) -> None:
    classes = sorted(train[LABEL].unique())
    frame = pd.DataFrame(proba, columns=classes)
    frame.insert(0, ID, train[ID].to_numpy())
    frame.insert(1, "fold", folds)
    frame.insert(2, LABEL, train[LABEL].to_numpy())
    frame.insert(3, PROMPT, train[PROMPT].to_numpy())
    Path(out).mkdir(parents=True, exist_ok=True)
    frame.to_parquet(Path(out) / "oof_transformer.parquet", index=False)


def main() -> None:
    args = parser().parse_args()
    train, _ = load(args.data)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    tokenizer = load_tokenizer(args.model)

    def build(n: int):
        return build_model(args.model, n, args.lora_r)

    proba, folds = run(train, args, build, tokenizer, device)
    write_oof(train, proba, folds, args.out)
    pred = proba.argmax(axis=1)
    classes = np.array(sorted(train[LABEL].unique()))
    print("overall:", balanced_accuracy(train[LABEL], classes[pred]))


if __name__ == "__main__":
    main()
