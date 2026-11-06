"""Metrics specific to this study. General statistics live in `forge`."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from forge.stats import PairedDifference, _cluster_sums, _weights

from .audit import surfaces
from .data import Sentence
from .spans import bio_spans


def _f1(rows: np.ndarray) -> float:
    tp, fp, fn = rows
    return float(2 * tp / max(2 * tp + fp + fn, 1e-9))


def paired_f1_difference(
    a: np.ndarray,
    b: np.ndarray,
    docs: Sequence[str],
    *,
    n_boot: int = 5000,
    alpha: float = 0.05,
    seed: int = 0,
) -> PairedDifference:
    """F1(a) - F1(b) on the same articles. Same resample for both, so article effects cancel."""
    sa, sb = _cluster_sums(np.asarray(a), docs), _cluster_sums(np.asarray(b), docs)
    k = len(sa)
    w = _weights(k, n_boot, np.random.default_rng(seed))
    ta, tb = w @ sa, w @ sb
    fa = 2 * ta[:, 0] / np.maximum(2 * ta[:, 0] + ta[:, 1] + ta[:, 2], 1e-9)
    fb = 2 * tb[:, 0] / np.maximum(2 * tb[:, 0] + tb[:, 1] + tb[:, 2], 1e-9)
    diff = fa - fb
    low, high = np.quantile(diff, [alpha / 2, 1 - alpha / 2])
    far = min((diff <= 0).mean(), (diff >= 0).mean())
    p = float(min(1.0, max(2 * far, 1 / n_boot)))
    fa0, fb0 = _f1(sa.sum(0)), _f1(sb.sum(0))
    return PairedDifference(fa0, fb0, fa0 - fb0, float(low), float(high), p, k)


def recall_by_seen(
    train: Sequence[Sentence], test: Sequence[Sentence], predictions: Sequence[Sequence[str]]
) -> dict:
    """Recall on gold mentions, split by whether the lowercased string occurred in training."""
    seen = {text for text, _ in surfaces(train)}
    hits = {True: 0, False: 0}
    totals = {True: 0, False: 0}
    for s, tags in zip(test, predictions):
        predicted = set(bio_spans(tags))
        for span in bio_spans(s.tags):
            known = " ".join(s.tokens[span[0] : span[1]]).lower() in seen
            totals[known] += 1
            hits[known] += span in predicted
    return {
        "seen_mentions": totals[True],
        "unseen_mentions": totals[False],
        "recall_seen": hits[True] / max(totals[True], 1),
        "recall_unseen": hits[False] / max(totals[False], 1),
        "gap": hits[True] / max(totals[True], 1) - hits[False] / max(totals[False], 1),
    }


def entity_ece(confidence: np.ndarray, correct: np.ndarray, bins: int = 15) -> float:
    """Expected calibration error with equal-count bins."""
    order = np.argsort(confidence, kind="stable")
    total = 0.0
    for group in np.array_split(order, bins):
        if len(group):
            gap = abs(confidence[group].mean() - correct[group].mean())
            total += gap * len(group) / len(order)
    return float(total)
