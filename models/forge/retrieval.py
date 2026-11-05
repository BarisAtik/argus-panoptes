"""Ranking metrics. `scores` is (queries, docs); `relevant` a same-shaped boolean matrix."""

from __future__ import annotations

import numpy as np


def _sorted_relevance(scores: np.ndarray, relevant: np.ndarray) -> np.ndarray:
    # Tie-break on document index so results are deterministic.
    order = np.argsort(-scores, axis=1, kind="stable")
    return np.take_along_axis(relevant, order, axis=1)


def average_precision(scores: np.ndarray, relevant: np.ndarray) -> np.ndarray:
    hits = _sorted_relevance(scores, relevant).astype(float)
    precision = np.cumsum(hits, axis=1) / np.arange(1, hits.shape[1] + 1)
    totals = hits.sum(axis=1)
    return np.divide((precision * hits).sum(axis=1), totals, out=np.zeros_like(totals),
                     where=totals > 0)


def precision_at_k(scores: np.ndarray, relevant: np.ndarray, k: int) -> np.ndarray:
    return _sorted_relevance(scores, relevant)[:, :k].mean(axis=1)


def recall_at_k(scores: np.ndarray, relevant: np.ndarray, k: int) -> np.ndarray:
    hits = _sorted_relevance(scores, relevant)
    totals = hits.sum(axis=1).astype(float)
    return np.divide(hits[:, :k].sum(axis=1).astype(float), totals, out=np.zeros_like(totals),
                     where=totals > 0)


def reciprocal_rank(scores: np.ndarray, relevant: np.ndarray) -> np.ndarray:
    hits = _sorted_relevance(scores, relevant)
    first = hits.argmax(axis=1)
    return np.where(hits.any(axis=1), 1.0 / (first + 1), 0.0)
