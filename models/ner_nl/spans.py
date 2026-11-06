"""Entity spans and exact-match scoring, per article so that intervals can resample articles."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

import numpy as np

from forge.stats import ratio_ci, ratio_ci_t

from .data import Sentence

ALL_LABELS = ("PER", "LOC", "ORG", "MISC")
SHARED_LABELS = ("PER", "LOC", "ORG")  # MISC is not comparable across annotation schemes


def bio_spans(tags: Sequence[str]) -> list[tuple[int, int, str]]:
    """(start, end, label) with end exclusive. A stray I- opens a span, as conlleval does."""
    spans, start, label = [], None, None
    for i, tag in enumerate(tags):
        prefix, _, kind = tag.partition("-")
        if prefix == "I" and kind == label:
            continue
        if label is not None:
            spans.append((start, i, label))
        start, label = (i, kind) if prefix in ("B", "I") else (None, None)
    if label is not None:
        spans.append((start, len(tags), label))
    return spans


def spans_to_bio(spans: Iterable[tuple[int, int, str]], length: int) -> list[str]:
    tags = ["O"] * length
    for start, end, label in spans:
        tags[start] = f"B-{label}"
        for i in range(start + 1, end):
            tags[i] = f"I-{label}"
    return tags


def count_by_doc(
    sentences: Sequence[Sentence],
    predictions: Sequence[Sequence[str]],
    labels: Sequence[str] = ALL_LABELS,
) -> tuple[np.ndarray, list[str]]:
    """Return (rows of tp, fp, fn; article ids), one row per sentence."""
    if len(sentences) != len(predictions):
        raise ValueError("one prediction per sentence is required")
    rows = np.zeros((len(sentences), 3))
    for i, (sentence, predicted) in enumerate(zip(sentences, predictions)):
        if len(predicted) != len(sentence.tokens):
            raise ValueError(f"sentence {i}: prediction length differs from tokens")
        gold = {s for s in bio_spans(sentence.tags) if s[2] in labels}
        pred = {s for s in bio_spans(predicted) if s[2] in labels}
        rows[i] = len(gold & pred), len(pred - gold), len(gold - pred)
    return rows, [s.doc_id for s in sentences]


def f1_interval(rows: np.ndarray, docs: Sequence[str], seed: int = 0, small: bool = False):
    """F1 is 2TP / (2TP + FP + FN), a ratio of sums: exactly what the forge intervals handle."""
    tp, fp, fn = rows.T
    num, den = 2 * tp, 2 * tp + fp + fn
    if small:
        return ratio_ci_t(num, den, docs)
    return ratio_ci(num, den, docs, seed=seed)


def prf(rows: np.ndarray) -> dict:
    tp, fp, fn = rows.sum(axis=0)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * tp / (2 * tp + fp + fn) if tp else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": fp, "fn": fn}
