"""Optional transformer track: same folds, same OOF format, so `ntl.failure` and R work unchanged.

    python -m ntl.hf_train --data data/raw --model microsoft/deberta-v3-small --out artifacts/deberta

Needs a GPU to be useful, and a model snapshot attached as a Kaggle dataset for offline runs.
Fold models are saved only with --save-models; weights stay out of git.
"""
from __future__ import annotations

import argparse
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
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    steps = max(1, len(loader) * args.epochs)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=args.lr, total_steps=steps)
    model.to(device).train()
    for _ in range(args.epochs):
        for batch, y in loader:
            batch = {k: x.to(device) for k, x in batch.items()}
            loss = cross_entropy(model(**batch).logits, y.to(device),
                                 label_smoothing=args.label_smoothing)
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
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


def run(train: pd.DataFrame, args, build_model, tokenizer, device) -> tuple[np.ndarray, np.ndarray]:
    classes = np.array(sorted(train[LABEL].unique()))
    y = np.searchsorted(classes, train[LABEL].to_numpy())
    folds = grouped_folds(train, args.folds, args.seed)
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
    tokenizer = AutoTokenizer.from_pretrained(args.model)

    def build(n: int):
        return AutoModelForSequenceClassification.from_pretrained(args.model, num_labels=n)

    proba, folds = run(train, args, build, tokenizer, device)
    write_oof(train, proba, folds, args.out)
    pred = proba.argmax(axis=1)
    classes = np.array(sorted(train[LABEL].unique()))
    print("overall:", balanced_accuracy(train[LABEL], classes[pred]))


if __name__ == "__main__":
    main()
