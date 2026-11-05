"""Datasets as plain Python: texts + labels, so every step can be tested without downloads."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

LABEL_NAMES = ("negatief", "positief")


@dataclass
class Split:
    texts: list[str]
    labels: list[int]

    def __len__(self) -> int:
        return len(self.texts)

    def subset(self, indices) -> Split:
        return Split([self.texts[i] for i in indices], [self.labels[i] for i in indices])


def load_dbrd() -> dict[str, Split]:
    """Dutch Book Reviews Dataset (CC BY-NC-SA 4.0, so non-commercial; see the model card)."""
    from datasets import load_dataset

    raw = load_dataset("benjaminvdb/dbrd")
    return {
        name: Split(list(raw[name]["text"]), [int(x) for x in raw[name]["label"]])
        for name in ("train", "test")
    }


def load_jsonl(path: str | Path) -> Split:
    texts, labels = [], []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                texts.append(row["text"])
                labels.append(int(row["label"]))
    return Split(texts, labels)
