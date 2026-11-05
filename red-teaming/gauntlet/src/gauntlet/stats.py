"""Statistics for small, clustered evaluations. Standard library only.

Trials from one scenario are not independent, so a plain binomial interval over
all trials is too narrow. The headline interval here is a cluster bootstrap over
scenarios; the Wilson interval is shown for comparison.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Iterable, Sequence


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value from discordant pair counts."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2**n
    return min(1.0, 2 * tail)


def cluster_bootstrap(values_by_cluster: dict[str, Sequence[float]], reps: int = 2000, seed: int = 7) -> tuple[float, float]:
    """Percentile interval of the mean, resampling whole clusters."""
    keys = sorted(values_by_cluster)
    if not keys:
        return (0.0, 1.0)
    rng = random.Random(seed)
    means = []
    for _ in range(reps):
        pool: list[float] = []
        for _ in keys:
            pool.extend(values_by_cluster[rng.choice(keys)])
        means.append(sum(pool) / len(pool))
    means.sort()
    return means[int(0.025 * reps)], means[min(reps - 1, int(0.975 * reps))]


def reproducibility(successes: int, trials: int, threshold: float = 0.5) -> dict[str, float | bool]:
    """Does the lower Wilson bound clear a program's reproducibility threshold?
    Useful when a program asks for behaviour that reproduces at least half the time."""
    lo, hi = wilson(successes, trials)
    return {"rate": successes / trials if trials else 0.0, "low": lo, "high": hi, "clears": lo >= threshold}


def trials_needed(p: float, threshold: float = 0.5, max_n: int = 2000) -> int | None:
    """Smallest n at which a true rate p yields a lower bound above threshold."""
    for n in range(1, max_n):
        if wilson(round(p * n), n)[0] >= threshold:
            return n
    return None


def power_two_defenses(asr_a: float, asr_b: float, scenarios: int, seeds: int, spread: float = 1.0,
                       sims: int = 400, seed: int = 11) -> float:
    """Simulated power of a paired comparison when scenarios vary in difficulty.

    Each scenario draws a logit offset ~ N(0, spread). Seeds within a scenario are
    then Bernoulli. A comparison counts as detected when exact McNemar on
    scenario-majority outcomes gives p < 0.05, which respects the clustering.
    """
    rng = random.Random(seed)

    def logit(p: float) -> float:
        return math.log(p / (1 - p))

    def expit(x: float) -> float:
        return 1 / (1 + math.exp(-x))

    hits = 0
    for _ in range(sims):
        b = c = 0
        for _ in range(scenarios):
            u = rng.gauss(0, spread)
            pa, pb = expit(logit(asr_a) + u), expit(logit(asr_b) + u)
            ya = sum(rng.random() < pa for _ in range(seeds)) * 2 > seeds
            yb = sum(rng.random() < pb for _ in range(seeds)) * 2 > seeds
            b += ya and not yb
            c += yb and not ya
        hits += mcnemar_exact(b, c) < 0.05
    return hits / sims


def group(rows: Iterable[dict], key: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        out[r[key]].append(r)
    return dict(out)
