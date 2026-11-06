"""Statistics for the evaluation. Small, and tested on cases with known answers."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

import numpy as np


def parent(technique: str) -> str:
    return technique.split(".")[0]


def on_target(rule_techniques: Iterable[str], dataset_techniques: Iterable[str]) -> bool:
    """Compared at parent level: T1059.001 counts for T1059."""
    return bool({parent(t) for t in rule_techniques} & {parent(t) for t in dataset_techniques})


def wilson(successes: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def _binomial_tail(k: int, n: int) -> float:
    """P(X >= k) for X ~ Binomial(n, 0.5)."""
    return sum(math.comb(n, i) for i in range(k, n + 1)) / 2**n


def mcnemar_one_sided(better_only: int, worse_only: int) -> float:
    """Exact sign test on discordant pairs: is the variant better than the baseline?"""
    n = better_only + worse_only
    return 1.0 if n == 0 else _binomial_tail(better_only, n)


def holm(p_values: dict[str, float]) -> dict[str, float]:
    ordered = sorted(p_values.items(), key=lambda item: item[1])
    adjusted: dict[str, float] = {}
    running = 0.0
    for rank, (name, p) in enumerate(ordered):
        running = max(running, min(1.0, p * (len(ordered) - rank)))
        adjusted[name] = running
    return adjusted


def clustered_permutation(
    outcome: Sequence[int],
    group: Sequence[int],
    cluster: Sequence[str],
    rounds: int = 20000,
    seed: int = 7,
) -> tuple[float, float]:
    """Difference in mean outcome, group 1 minus group 0, keeping each cluster's rows together.

    The group label is shuffled between clusters, so many rows from one rule count as one unit
    of evidence. Returns the difference and a one-sided p-value for 'greater than zero'.
    """
    outcome_array = np.asarray(outcome, dtype=float)
    group_array = np.asarray(group, dtype=int)
    names = sorted(set(cluster))
    index = {name: i for i, name in enumerate(names)}
    ids = np.array([index[name] for name in cluster])
    cluster_group = np.zeros(len(names), dtype=int)
    cluster_group[ids] = group_array
    if not np.array_equal(cluster_group[ids], group_array):
        raise ValueError("a cluster must sit entirely in one group")
    totals = np.bincount(ids, weights=outcome_array, minlength=len(names))
    sizes = np.bincount(ids, minlength=len(names)).astype(float)

    def difference(labels: np.ndarray) -> float:
        one = labels == 1
        return totals[one].sum() / sizes[one].sum() - totals[~one].sum() / sizes[~one].sum()

    observed = float(difference(cluster_group))
    rng = np.random.default_rng(seed)
    at_least = sum(
        difference(rng.permutation(cluster_group)) >= observed - 1e-12 for _ in range(rounds)
    )
    return observed, (at_least + 1) / (rounds + 1)
