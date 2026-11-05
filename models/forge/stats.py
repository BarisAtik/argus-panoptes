"""Uncertainty estimates that respect how the data was collected.

Clips from one speaker (or reviews from one author) are not independent. Resampling clips
gives intervals that are too narrow, so everything here resamples *clusters*. The effect is
measured, not assumed: see `forge.simulate` and docs/ci_coverage_simulation.md.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass

import numpy as np
from scipy import stats as sps


@dataclass(frozen=True)
class Interval:
    estimate: float
    low: float
    high: float
    n_clusters: int

    def as_dict(self) -> dict:
        return asdict(self)

    def __str__(self) -> str:
        return f"{self.estimate:.4f} [{self.low:.4f}, {self.high:.4f}]"


def _cluster_sums(values: np.ndarray, clusters: Sequence | None) -> np.ndarray:
    """Sum `values` (n_items, ...) per cluster; every item is its own cluster if None."""
    if clusters is None:
        return values
    if len(clusters) != len(values):
        raise ValueError("clusters and values must have the same length")
    _, inverse = np.unique(np.asarray(clusters, dtype=object).astype(str), return_inverse=True)
    out = np.zeros((inverse.max() + 1, *values.shape[1:]), dtype=float)
    np.add.at(out, inverse, values)
    return out


def _weights(n: int, n_boot: int, rng: np.random.Generator) -> np.ndarray:
    return rng.multinomial(n, np.full(n, 1.0 / n), size=n_boot).astype(float)


def ratio_ci(
    numerator: Sequence[float],
    denominator: Sequence[float],
    clusters: Sequence | None = None,
    *,
    n_boot: int = 2000,
    alpha: float = 0.05,
    seed: int = 0,
) -> Interval:
    """Percentile bootstrap CI for sum(numerator) / sum(denominator), resampling clusters.

    WER is a ratio of sums, so this is the right statistic for it (a mean of per-clip WER would
    overweight short clips). Mean accuracy is the special case denominator = 1.
    """
    num = np.asarray(numerator, dtype=float)
    den = np.asarray(denominator, dtype=float)
    if num.shape != den.shape or num.ndim != 1:
        raise ValueError("numerator and denominator must be 1-d and the same length")
    if den.sum() <= 0:
        raise ValueError("denominator sums to zero")
    pairs = _cluster_sums(np.column_stack([num, den]), clusters)
    k = len(pairs)
    w = _weights(k, n_boot, np.random.default_rng(seed))
    tops, bottoms = w @ pairs[:, 0], w @ pairs[:, 1]
    boot = tops[bottoms > 0] / bottoms[bottoms > 0]
    low, high = np.quantile(boot, [alpha / 2, 1 - alpha / 2])
    return Interval(float(num.sum() / den.sum()), float(low), float(high), k)


def ratio_ci_t(
    numerator: Sequence[float],
    denominator: Sequence[float],
    clusters: Sequence,
    *,
    alpha: float = 0.05,
) -> Interval:
    """Cluster-robust t interval for a ratio of sums (linearized, with a small-sample factor).

    Meant for small groups, where a percentile bootstrap runs narrow: see
    `docs/small_group_coverage.md`.
    """
    from scipy import stats as sps

    num = np.asarray(numerator, dtype=float)
    den = np.asarray(denominator, dtype=float)
    pairs = _cluster_sums(np.column_stack([num, den]), clusters)
    k = len(pairs)
    if k < 2:
        raise ValueError("need at least two clusters")
    ratio = pairs[:, 0].sum() / pairs[:, 1].sum()
    residuals = pairs[:, 0] - ratio * pairs[:, 1]
    se = np.sqrt(k / (k - 1) * np.sum(residuals**2)) / pairs[:, 1].sum()
    half = float(sps.t.ppf(1 - alpha / 2, k - 1) * se)
    return Interval(float(ratio), float(ratio - half), float(ratio + half), k)


def mean_ci(values: Sequence[float], clusters: Sequence | None = None, **kwargs) -> Interval:
    values = np.asarray(values, dtype=float)
    return ratio_ci(values, np.ones_like(values), clusters, **kwargs)


@dataclass(frozen=True)
class PairedDifference:
    a: float
    b: float
    difference: float  # a - b
    low: float
    high: float
    p_value: float
    n_clusters: int

    def as_dict(self) -> dict:
        return asdict(self)


def paired_ratio_difference(
    numerator_a: Sequence[float],
    numerator_b: Sequence[float],
    denominator: Sequence[float],
    clusters: Sequence | None = None,
    *,
    n_boot: int = 5000,
    alpha: float = 0.05,
    seed: int = 0,
) -> PairedDifference:
    """Compare two systems on the *same* items; pairing removes between-speaker variance.

    The p-value is a two-sided bootstrap p-value (twice the share of resamples on the far side
    of zero, floored at 1/n_boot so it never reports an impossible exact zero).
    """
    a, b, den = (np.asarray(x, dtype=float) for x in (numerator_a, numerator_b, denominator))
    if not (a.shape == b.shape == den.shape):
        raise ValueError("inputs must have the same shape")
    triples = _cluster_sums(np.column_stack([a, b, den]), clusters)
    k = len(triples)
    w = _weights(k, n_boot, np.random.default_rng(seed))
    bottoms = w @ triples[:, 2]
    ok = bottoms > 0
    diffs = ((w @ triples[:, 0]) - (w @ triples[:, 1]))[ok] / bottoms[ok]
    low, high = np.quantile(diffs, [alpha / 2, 1 - alpha / 2])
    side = min((diffs <= 0).mean(), (diffs >= 0).mean())
    p = float(np.clip(2 * side, 1.0 / n_boot, 1.0))
    est_a, est_b = a.sum() / den.sum(), b.sum() / den.sum()
    return PairedDifference(float(est_a), float(est_b), float(est_a - est_b), float(low),
                            float(high), p, k)


def mcnemar_exact(correct_a: Sequence[bool], correct_b: Sequence[bool]) -> dict:
    """Exact McNemar test for two classifiers scored on the same examples."""
    a, b = np.asarray(correct_a, dtype=bool), np.asarray(correct_b, dtype=bool)
    only_a, only_b = int((a & ~b).sum()), int((~a & b).sum())
    n = only_a + only_b
    p = 1.0 if n == 0 else float(sps.binomtest(only_a, n, 0.5).pvalue)
    return {"only_a_correct": only_a, "only_b_correct": only_b, "p_value": p}


def holm(p_values: Sequence[float]) -> list[float]:
    """Holm-Bonferroni adjusted p-values, in the input order."""
    p = np.asarray(p_values, dtype=float)
    order = np.argsort(p)
    adjusted = np.empty_like(p)
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, (len(p) - rank) * p[idx])
        adjusted[idx] = min(1.0, running)
    return adjusted.tolist()


def wilson_interval(successes: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    z = sps.norm.ppf(1 - alpha / 2)
    p = successes / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return (float(max(0.0, centre - half)), float(min(1.0, centre + half)))
