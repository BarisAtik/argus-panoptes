"""Metrics that say how a detector behaves at a threshold chosen before seeing the test set."""

from __future__ import annotations

import numpy as np
from sklearn.metrics import roc_auc_score


def auroc(y: np.ndarray, s: np.ndarray) -> float:
    return float(roc_auc_score(y, s)) if len(set(y.tolist())) == 2 else float("nan")


def threshold_at_fpr(neg_scores: np.ndarray, fpr: float) -> float:
    """Smallest threshold whose FPR on these negatives is at most `fpr`."""
    s = np.sort(neg_scores)
    k = int(np.ceil(len(s) * (1 - fpr)))
    return float(s[min(k, len(s) - 1)]) + 1e-9


def rates(y: np.ndarray, s: np.ndarray, tau: float) -> dict[str, float]:
    p = s >= tau
    return {"recall": float(p[y == 1].mean()) if (y == 1).any() else float("nan"),
            "fpr": float(p[y == 0].mean()) if (y == 0).any() else float("nan")}


def recall_at_fpr(y: np.ndarray, s: np.ndarray, fpr: float) -> float:
    return rates(y, s, threshold_at_fpr(s[y == 0], fpr))["recall"]


def ece(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0, 1, bins + 1)
    total = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (p >= lo) & (p < hi if hi < 1 else p <= hi)
        if m.any():
            total += m.mean() * abs(p[m].mean() - y[m].mean())
    return float(total)


def cluster_auc_ci(y: np.ndarray, s: np.ndarray, groups: np.ndarray, n: int = 300, seed: int = 0) -> tuple[float, float]:
    """Bootstrap over payload templates. Documents from one template are not independent."""
    rng = np.random.default_rng(seed)
    pos_groups = np.unique(groups[y == 1])
    neg = np.where(y == 0)[0]
    by = {g: np.where((groups == g) & (y == 1))[0] for g in pos_groups}
    vals = []
    for _ in range(n):
        take = rng.choice(pos_groups, len(pos_groups))
        idx = np.concatenate([by[g] for g in take] + [rng.choice(neg, len(neg))])
        vals.append(auroc(y[idx], s[idx]))
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))
