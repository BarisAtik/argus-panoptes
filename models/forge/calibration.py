"""Does a model's confidence mean anything? Calibration and selective prediction."""

from __future__ import annotations

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import log_softmax, softmax


def nll(logits: np.ndarray, labels: np.ndarray, temperature: float = 1.0) -> float:
    logp = log_softmax(np.asarray(logits, dtype=float) / temperature, axis=1)
    return float(-logp[np.arange(len(labels)), labels].mean())


def fit_temperature(logits: np.ndarray, labels: np.ndarray) -> float:
    """Single-parameter scaling. Fit on validation data, never on the test set."""
    logits, labels = np.asarray(logits, dtype=float), np.asarray(labels)
    result = minimize_scalar(
        lambda log_t: nll(logits, labels, float(np.exp(log_t))),
        bounds=(np.log(0.05), np.log(20.0)),
        method="bounded",
    )
    return float(np.exp(result.x))


def probabilities(logits: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    return softmax(np.asarray(logits, dtype=float) / temperature, axis=1)


def brier(probs: np.ndarray, labels: np.ndarray) -> float:
    one_hot = np.eye(probs.shape[1])[labels]
    return float(((probs - one_hot) ** 2).sum(axis=1).mean())


def reliability_table(
    probs: np.ndarray, labels: np.ndarray, n_bins: int = 15, adaptive: bool = True
) -> list[dict]:
    """Top-label bins. Adaptive = equal-count, more stable than equal-width on confident models."""
    confidence = probs.max(axis=1)
    correct = probs.argmax(axis=1) == labels
    if adaptive:
        order = np.argsort(confidence, kind="stable")
        groups = [g for g in np.array_split(order, n_bins) if len(g)]
    else:
        edges = np.linspace(0, 1, n_bins + 1)
        index = np.clip(np.digitize(confidence, edges[1:-1]), 0, n_bins - 1)
        groups = [np.flatnonzero(index == b) for b in range(n_bins)]
        groups = [g for g in groups if len(g)]
    return [
        {
            "n": int(len(g)),
            "confidence": float(confidence[g].mean()),
            "accuracy": float(correct[g].mean()),
        }
        for g in groups
    ]


def ece(probs: np.ndarray, labels: np.ndarray, n_bins: int = 15, adaptive: bool = True) -> float:
    table = reliability_table(probs, labels, n_bins, adaptive)
    total = sum(row["n"] for row in table)
    return float(sum(row["n"] / total * abs(row["accuracy"] - row["confidence"]) for row in table))


def risk_coverage(confidence: np.ndarray, loss: np.ndarray) -> dict:
    """Mean loss on the most confident `coverage` share of items, for every coverage.

    `loss` may be 0/1 errors or a per-item error rate. The area under the curve (AURC) is low
    when the score ranks bad items last. Compare against `oracle_aurc` and `random_aurc`:
    a score is only useful as a review filter if it clearly beats random.
    """
    confidence, loss = np.asarray(confidence, dtype=float), np.asarray(loss, dtype=float)
    n = len(loss)
    order = np.argsort(-confidence, kind="stable")
    coverage = np.arange(1, n + 1) / n
    risk = np.cumsum(loss[order]) / np.arange(1, n + 1)
    oracle = np.cumsum(np.sort(loss)) / np.arange(1, n + 1)
    return {
        "coverage": coverage,
        "risk": risk,
        "aurc": float(risk.mean()),
        "oracle_aurc": float(oracle.mean()),
        "random_aurc": float(loss.mean()),
    }


def risk_at(curve: dict, coverages=(0.5, 0.8, 0.9, 1.0)) -> dict[str, float]:
    n = len(curve["risk"])
    return {f"{c:.2f}": float(curve["risk"][max(0, int(round(c * n)) - 1)]) for c in coverages}
