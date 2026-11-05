"""Fine-tune a Hugging Face sequence classifier with a plain PyTorch loop.

A short explicit loop instead of `Trainer`: fewer moving parts across library versions, and
head+tail truncation is a one-line choice. Reviews tend to state their verdict at the end, so
keeping only the head of a long text throws away evidence.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from text_nl.data import Split


@dataclass
class TrainConfig:
    model: str = "pdelobelle/robbert-v2-dutch-base"
    max_length: int = 256
    truncation: str = "head_tail"  # or "head"
    batch_size: int = 16
    lr: float = 2e-5
    weight_decay: float = 0.01
    epochs: int = 3
    warmup_fraction: float = 0.1
    grad_accumulation: int = 1
    patience: int = 1
    seed: int = 0
    device: str | None = None


def _special_tokens(tokenizer) -> tuple[list[int], list[int]]:
    """The tokens the tokenizer wraps a text in ([CLS]/[SEP], <s>/</s>, ...), found by probing."""
    plain = tokenizer("woord", add_special_tokens=False)["input_ids"]
    full = tokenizer("woord", add_special_tokens=True)["input_ids"]
    start = next(i for i in range(len(full)) if full[i : i + len(plain)] == plain)
    return full[:start], full[start + len(plain) :]


def encode(tokenizer, texts: list[str], max_length: int, truncation: str) -> dict:
    """Tokenize; for "head_tail" keep the start and the end of texts that don't fit."""
    prefix, suffix = _special_tokens(tokenizer)
    room = max_length - len(prefix) - len(suffix)
    ids = tokenizer(texts, add_special_tokens=False, truncation=False)["input_ids"]
    if truncation == "head_tail":
        head = room // 2
        tail = room - head
        ids = [seq if len(seq) <= room else seq[:head] + seq[-tail:] for seq in ids]
    elif truncation == "head":
        ids = [seq[:room] for seq in ids]
    else:
        raise ValueError(f"unknown truncation {truncation!r}")
    return {"input_ids": [prefix + seq + suffix for seq in ids]}


def _pad(tokenizer, encoded: list[list[int]], device):
    import torch

    width = max(map(len, encoded))
    pad_id = tokenizer.pad_token_id if tokenizer.pad_token_id is not None else 0
    ids = torch.full((len(encoded), width), pad_id, dtype=torch.long)
    mask = torch.zeros((len(encoded), width), dtype=torch.long)
    for row, seq in enumerate(encoded):
        ids[row, : len(seq)] = torch.tensor(seq)
        mask[row, : len(seq)] = 1
    return ids.to(device), mask.to(device)


def predict_logits(model, tokenizer, texts, config: TrainConfig, device) -> np.ndarray:
    import torch

    model.eval()
    encoded = encode(tokenizer, texts, config.max_length, config.truncation)["input_ids"]
    order = np.argsort([len(seq) for seq in encoded])  # similar lengths batch with less padding
    chunks = []
    with torch.inference_mode():
        for start in range(0, len(order), config.batch_size * 2):
            batch = order[start : start + config.batch_size * 2]
            ids, mask = _pad(tokenizer, [encoded[i] for i in batch], device)
            chunks.append(model(input_ids=ids, attention_mask=mask).logits.float().cpu().numpy())
    output = np.empty((len(texts), chunks[0].shape[1]))
    output[order] = np.concatenate(chunks)
    return output


def fit(
    train: Split,
    val: Split,
    config: TrainConfig,
    out_dir: str | Path | None = None,
    model=None,
    tokenizer=None,
):
    """Train with early stopping on validation NLL. Returns (model, tokenizer, history)."""
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    from forge.calibration import nll

    torch.manual_seed(config.seed)
    np.random.seed(config.seed)
    device = config.device or ("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = tokenizer or AutoTokenizer.from_pretrained(config.model)
    model = model or AutoModelForSequenceClassification.from_pretrained(config.model, num_labels=2)
    model.to(device)

    encoded = encode(tokenizer, train.texts, config.max_length, config.truncation)["input_ids"]
    labels = torch.tensor(train.labels, device=device)
    decay = [p for n, p in model.named_parameters() if not n.endswith(("bias", "LayerNorm.weight"))]
    no_decay = [p for n, p in model.named_parameters() if n.endswith(("bias", "LayerNorm.weight"))]
    optimizer = torch.optim.AdamW(
        [{"params": decay, "weight_decay": config.weight_decay},
         {"params": no_decay, "weight_decay": 0.0}],
        lr=config.lr,
    )
    steps_per_epoch = max(1, len(encoded) // (config.batch_size * config.grad_accumulation))
    total_steps = steps_per_epoch * config.epochs
    warmup = int(config.warmup_fraction * total_steps)
    scheduler = torch.optim.lr_scheduler.LambdaLR(
        optimizer,
        lambda step: (step + 1) / max(1, warmup) if step < warmup
        else max(0.0, (total_steps - step) / max(1, total_steps - warmup)),
    )
    scaler = torch.amp.GradScaler("cuda", enabled=device == "cuda")
    rng = np.random.default_rng(config.seed)
    history, best_nll, best_state, stale = [], float("inf"), None, 0

    for epoch in range(config.epochs):
        model.train()
        order = rng.permutation(len(encoded))
        running = 0.0
        for step, start in enumerate(range(0, len(order), config.batch_size)):
            batch = order[start : start + config.batch_size]
            ids, mask = _pad(tokenizer, [encoded[i] for i in batch], device)
            with torch.autocast(device_type=device.split(":")[0], enabled=device == "cuda"):
                loss = model(input_ids=ids, attention_mask=mask,
                             labels=labels[batch]).loss / config.grad_accumulation
            scaler.scale(loss).backward()
            running += loss.item() * config.grad_accumulation
            if (step + 1) % config.grad_accumulation == 0:
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                scaler.step(optimizer)
                scaler.update()
                scheduler.step()
                optimizer.zero_grad(set_to_none=True)
        val_logits = predict_logits(model, tokenizer, val.texts, config, device)
        val_nll = nll(val_logits, np.array(val.labels))
        accuracy = float((val_logits.argmax(axis=1) == np.array(val.labels)).mean())
        steps = max(1, len(range(0, len(order), config.batch_size)))
        history.append({"epoch": epoch + 1, "train_loss": running / steps, "val_nll": val_nll,
                        "val_accuracy": accuracy})
        print(json.dumps(history[-1]), flush=True)
        if val_nll < best_nll:
            best_nll, stale = val_nll, 0
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        else:
            stale += 1
            if stale > config.patience:
                break
    if best_state is not None:
        model.load_state_dict(best_state)
    if out_dir:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        model.save_pretrained(out)
        tokenizer.save_pretrained(out)
        (out / "train_history.json").write_text(
            json.dumps({"config": asdict(config), "history": history}, indent=2), encoding="utf-8"
        )
    return model, tokenizer, history
