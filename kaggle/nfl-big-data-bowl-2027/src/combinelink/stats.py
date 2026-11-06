"""The reliability and validity chain: can this metric carry signal, and does it?"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def icc1(df: pd.DataFrame, subject: str, value: str) -> dict[str, float]:
    """Attempt-to-attempt repeatability: one-way ICC with unbalanced-design correction.

    `reliability_of_mean` is what matters when a player's attempts are averaged. A noisy metric
    caps any correlation with game outcomes, however real the underlying trait.
    """
    g = df.groupby(subject)[value]
    n, means, sizes = df[value].notna().sum(), g.mean(), g.count()
    k = len(sizes)
    grand = df[value].mean()
    ss_between = (sizes * (means - grand) ** 2).sum()
    ss_within = ((df[value] - g.transform("mean")) ** 2).sum()
    ms_between, ms_within = ss_between / (k - 1), ss_within / (n - k)
    n0 = (n - (sizes ** 2).sum() / n) / (k - 1)
    tau2 = max((ms_between - ms_within) / n0, 0.0)
    icc = tau2 / (tau2 + ms_within) if tau2 + ms_within > 0 else 0.0
    mean_n = float(sizes.mean())
    return {"icc": float(icc), "reliability_of_mean": float(mean_n * icc / (1 + (mean_n - 1) * icc)),
            "players": int(k), "attempts_per_player": mean_n}


def correlation_ceiling(rel_x: float, rel_y: float) -> float:
    """Largest observable correlation given two measurement reliabilities (Spearman)."""
    return float(np.sqrt(max(rel_x, 0) * max(rel_y, 0)))


def empirical_bayes(df: pd.DataFrame, subject: str, value: str) -> pd.DataFrame:
    """Shrink noisy per-player averages toward the mean; five targets should not outrank fifty."""
    stats = df.groupby(subject)[value].agg(["mean", "count"])
    res = df[value] - df.groupby(subject)[value].transform("mean")
    dof = max(len(df) - len(stats), 1)
    sigma2 = float((res ** 2).sum() / dof)
    grand = float(df[value].mean())
    tau2 = max(float(stats["mean"].var(ddof=1)) - float((sigma2 / stats["count"]).mean()), 0.0)
    weight = tau2 / (tau2 + sigma2 / stats["count"]) if tau2 > 0 else 0 * stats["count"]
    return pd.DataFrame({"raw": stats["mean"], "n": stats["count"], "shrunk":
                         grand + weight * (stats["mean"] - grand), "weight": weight})


def grouped_skill(x: np.ndarray, y: np.ndarray, position: np.ndarray, groups: np.ndarray,
                  n_splits: int = 5) -> float:
    """Out-of-player R2 over a position-mean baseline. Zero means no skill beyond position."""
    y_hat = np.zeros(len(y))
    base = np.zeros(len(y))
    frame = pd.DataFrame({"y": y, "pos": position})
    for fit, val in GroupKFold(n_splits).split(x, y, groups):
        means = frame.iloc[fit].groupby("pos")["y"].mean()
        fill = frame.iloc[fit]["y"].mean()
        base_fit = frame.iloc[fit]["pos"].map(means).to_numpy()
        base[val] = frame.iloc[val]["pos"].map(means).fillna(fill).to_numpy()
        model = make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-2, 4, 13)))
        model.fit(x[fit], y[fit] - base_fit)
        y_hat[val] = base[val] + model.predict(x[val])
    return float(1 - ((y - y_hat) ** 2).sum() / ((y - base) ** 2).sum())


def permutation_test(x: np.ndarray, y: np.ndarray, position: np.ndarray, groups: np.ndarray,
                     n_perm: int = 200, seed: int = 0) -> dict[str, float]:
    """Null: shuffle whole players' features within position, which keeps the role structure."""
    rng = np.random.default_rng(seed)
    frame = pd.DataFrame({"g": groups, "pos": position})
    players = frame.drop_duplicates("g").reset_index(drop=True)
    row_of = pd.Series(np.arange(len(frame)), index=frame.index).groupby(frame["g"]).first()
    x_by_player = x[row_of.loc[players["g"]].to_numpy()]
    observed = grouped_skill(x, y, position, groups)
    null = np.empty(n_perm)
    index = pd.Series(np.arange(len(players)), index=players["g"])
    for i in range(n_perm):
        perm = np.arange(len(players))
        for _, idx in players.groupby("pos").indices.items():
            perm[idx] = rng.permutation(perm[idx])
        null[i] = grouped_skill(x_by_player[perm][index.loc[groups].to_numpy()], y, position, groups)
    return {"observed_r2": observed, "null_mean": float(null.mean()),
            "p_value": float((1 + (null >= observed).sum()) / (n_perm + 1))}


def composite(players: pd.DataFrame, metrics: list[str]) -> pd.Series:
    """First principal component of z-scored metrics, for testing correlated metrics as one trait.

    Five metrics reflecting one trait are one finding, so this is the single primary test. It uses
    no outcome, so building it on all players leaks nothing. The sign follows the first metric.
    """
    z = players[metrics]
    z = (z - z.mean()) / z.std(ddof=1).replace(0, 1)
    z = z.fillna(0.0).to_numpy()
    if z.shape[1] == 1:
        return pd.Series(z[:, 0], index=players.index)
    vec = np.linalg.svd(z, full_matrices=False)[2][0]
    return pd.Series(z @ (vec * np.sign(vec[0] or 1.0)), index=players.index)


def minimum_detectable_effect(x: np.ndarray, y: np.ndarray, position: np.ndarray,
                              groups: np.ndarray, effects=(0.1, 0.2, 0.3, 0.5, 0.75, 1.0),
                              n_sim: int = 40, n_null: int = 100, power: float = 0.8,
                              seed: int = 0) -> dict:
    """The effect this sample could have detected, which is what makes a null result worth reading.

    Uses the real outcomes and player structure. Each simulation shuffles players within position
    to remove any real link, then adds a known effect in outcome units per SD of `x`. Detection
    means beating the 95th percentile of the no-effect R2.
    """
    rng = np.random.default_rng(seed)
    frame = pd.DataFrame({"g": groups, "pos": position, "x": np.ravel(x)})
    players = frame.drop_duplicates("g").reset_index(drop=True)
    std = players["x"].std(ddof=1) or 1.0
    players["x"] = (players["x"] - players["x"].mean()) / std
    row_player = pd.Series(np.arange(len(players)), index=players["g"]).loc[groups].to_numpy()

    def shuffled() -> np.ndarray:
        values = players["x"].to_numpy().copy()
        for idx in players.groupby("pos").indices.values():
            values[idx] = rng.permutation(values[idx])
        return values[row_player]

    def skill(beta: float) -> float:
        fake = shuffled()
        return grouped_skill(fake[:, None], y + beta * fake, position, groups)

    cut = float(np.quantile([skill(0.0) for _ in range(n_null)], 0.95))
    curve = {float(b): float(np.mean([skill(b) > cut for _ in range(n_sim)])) for b in effects}
    reached = [b for b, share in curve.items() if share >= power]
    return {"power_curve": curve, "null_r2_p95": cut,
            "min_detectable_per_sd": min(reached) if reached else None,
            "players": len(players), "rows": len(y)}


def benjamini_hochberg(p_values) -> np.ndarray:
    """Adjusted p-values; a project scanning many metrics needs this before claiming anything."""
    p = np.asarray(p_values, float)
    order = np.argsort(p)
    adj = p[order] * len(p) / np.arange(1, len(p) + 1)
    adj = np.minimum.accumulate(adj[::-1])[::-1]
    out = np.empty_like(adj)
    out[order] = np.minimum(adj, 1)
    return out


def selection_report(players: pd.DataFrame, metric: str, has_outcome: str, bins: int = 4) -> pd.Series:
    """Share of players with an outcome per metric quartile. Slower rookies may never see targets,
    so a flat result among those who played can still hide a real effect."""
    q = pd.qcut(players[metric], bins, labels=False, duplicates="drop")
    return players.groupby(q)[has_outcome].mean()
