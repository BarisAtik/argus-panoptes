"""Optional transductive step: recover hidden prompts in test, then give each model one passage.

Train looks like a prompt x model grid. If test has that shape too, passages on one prompt must
all have different authors, so independent argmax wastes information. This module:

1. clusters test passages by topic, capping a cluster at n_models;
2. within each cluster, solves the assignment problem so no model is used twice.

It only uses test *text*, no labels, but it is an assumption about how test was built. It is off
by default; see NOTES.md for what has to be true on real data before turning it on.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import adjusted_rand_score, balanced_accuracy_score
from sklearn.preprocessing import normalize


def distance_matrix(texts) -> np.ndarray:
    """Cosine distance on topic words. Computed sparse: dense pairwise distances take many minutes
    at test-set size, while this takes seconds."""
    vec = TfidfVectorizer(stop_words="english", sublinear_tf=True, min_df=1)
    x = normalize(vec.fit_transform(list(texts)))
    dist = 1 - (x @ x.T).toarray().astype(np.float32)
    np.fill_diagonal(dist, 0)
    return np.clip(dist, 0, None)


def _cluster(dist: np.ndarray, max_size: int, threshold: float) -> np.ndarray:
    labels = AgglomerativeClustering(n_clusters=None, distance_threshold=threshold,
                                     metric="precomputed", linkage="average").fit_predict(dist)
    return _cap_clusters(labels, dist, max_size)


def cluster_passages(texts, max_size: int = 18, distance_threshold: float = 0.9) -> np.ndarray:
    """Average-linkage clustering on topic words; oversize clusters are split afterwards."""
    texts = list(texts)
    if len(texts) < 2:
        return np.zeros(len(texts), dtype=int)
    return _cluster(distance_matrix(texts), max_size, distance_threshold)


def _cap_clusters(labels: np.ndarray, dist: np.ndarray, max_size: int) -> np.ndarray:
    out = labels.copy()
    next_id = out.max() + 1
    for c in np.unique(labels):
        idx = np.flatnonzero(labels == c)
        if len(idx) <= max_size:
            continue
        order = idx[np.argsort(dist[np.ix_(idx, idx)].mean(axis=1))]
        for start in range(max_size, len(order), max_size):
            out[order[start:start + max_size]] = next_id
            next_id += 1
    return out


def assign_within_clusters(proba: np.ndarray, clusters: np.ndarray,
                           min_size: int = 2) -> np.ndarray:
    """Return class indices maximising summed log-probability, with no class repeated in a cluster.

    Clusters smaller than `min_size` keep their argmax. Set it to the number of classes to trust
    only full clusters, which are the ones most likely to be a real prompt.
    """
    pred = proba.argmax(axis=1)
    log_p = np.log(np.clip(proba, 1e-12, 1.0))
    for c in np.unique(clusters):
        idx = np.flatnonzero(clusters == c)
        if len(idx) < max(min_size, 2) or len(idx) > proba.shape[1]:
            continue
        rows, cols = linear_sum_assignment(-log_p[idx])
        pred[idx[rows]] = cols
    return pred


def balance_classes(proba: np.ndarray, n_iter: int = 50) -> np.ndarray:
    """Rescale probabilities so each class gets an equal share of the predicted mass.

    If every model wrote about as many test passages, predicted shares should be even. Balanced
    accuracy pays for that, since a shy class costs as much as any other. This uses no labels and
    needs only the share of each class in test, not which passages share a prompt, so it rests on
    a much weaker assumption than `assign_within_clusters`.
    """
    p = np.clip(proba, 1e-12, 1.0)
    for _ in range(n_iter):
        p = p / (p.mean(axis=0, keepdims=True) * p.shape[1])
        p = p / p.sum(axis=1, keepdims=True)
    return p


def tune_threshold(texts, prompts, max_size: int = 18,
                   grid=(0.6, 0.7, 0.8, 0.85, 0.9, 0.95)) -> dict[float, float]:
    """Adjusted Rand index per distance threshold, on passages whose prompts are known."""
    dist = distance_matrix(texts)
    return {t: float(adjusted_rand_score(prompts, _cluster(dist, max_size, t))) for t in grid}


def stress_curve(proba: np.ndarray, y: np.ndarray, prompts: np.ndarray,
                 noise=(0.0, 0.1, 0.25, 0.5), keep=(1.0, 0.7), seed: int = 0) -> list[dict]:
    """How much does assignment help as its assumptions break?

    `noise` reassigns that share of rows to a random cluster, standing in for a worse clustering.
    `keep` subsamples rows, standing in for a test set where only some models answer each prompt.
    """
    rng = np.random.default_rng(seed)
    base = pd.factorize(prompts)[0]
    rows = []
    for k in keep:
        mask = rng.random(len(y)) < k
        for n in noise:
            clusters = base.copy()
            flip = rng.random(len(y)) < n
            clusters[flip] = rng.integers(0, base.max() + 1, flip.sum())
            pred = assign_within_clusters(proba[mask], clusters[mask])
            rows.append({
                "keep": k, "noise": n,
                "argmax": float(balanced_accuracy_score(y[mask], proba[mask].argmax(axis=1))),
                "assigned": float(balanced_accuracy_score(y[mask], pred)),
            })
    return rows
