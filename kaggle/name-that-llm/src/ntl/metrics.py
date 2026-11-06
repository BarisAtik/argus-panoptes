"""Scoring plus the uncertainty a single CV number hides."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score


def balanced_accuracy(y_true, y_pred) -> float:
    """The competition metric: mean per-model recall, every model weighted equally."""
    return float(balanced_accuracy_score(y_true, y_pred))


def per_model_recall(y_true, y_pred) -> pd.Series:
    frame = pd.DataFrame({"y": np.asarray(y_true), "p": np.asarray(y_pred)})
    return frame.assign(hit=frame.y == frame.p).groupby("y")["hit"].mean().sort_values()


def lab_accuracy(y_true, y_pred, lab_of: dict[str, str]) -> float:
    """Accuracy after collapsing models to their lab. The gap to model-level accuracy shows how
    much of the error is sibling confusion within one lab rather than a wrong family."""
    t = pd.Series(np.asarray(y_true)).map(lab_of)
    p = pd.Series(np.asarray(y_pred)).map(lab_of)
    if t.isna().any() or p.isna().any():
        raise ValueError("lab_of does not cover every model name")
    return float((t.to_numpy() == p.to_numpy()).mean())


def prompt_bootstrap_ci(y_true, y_pred, groups, n_boot: int = 1000, seed: int = 0,
                        level: float = 0.95) -> dict[str, float]:
    """CI for balanced accuracy, resampling whole prompts.

    Prompts are the unit the test set will sample, so they are what gets resampled. On the real-text
    proxy this was conservative: 10 of 10 holdouts fell inside it. See NOTES.md, including why the
    usual reason, that passages sharing a prompt are correlated, did not hold there.
    """
    y_true, y_pred, groups = map(np.asarray, (y_true, y_pred, groups))
    rng = np.random.default_rng(seed)
    uniq, inv = np.unique(groups, return_inverse=True)
    rows = [np.flatnonzero(inv == i) for i in range(len(uniq))]
    scores = np.empty(n_boot)
    for b in range(n_boot):
        pick = np.concatenate([rows[i] for i in rng.integers(0, len(uniq), len(uniq))])
        scores[b] = balanced_accuracy(y_true[pick], y_pred[pick])
    lo, hi = np.quantile(scores, [(1 - level) / 2, (1 + level) / 2])
    return {"point": balanced_accuracy(y_true, y_pred), "lo": float(lo), "hi": float(hi),
            "se": float(scores.std(ddof=1))}


def paired_prompt_bootstrap(y_true, pred_a, pred_b, groups, n_boot: int = 1000,
                            seed: int = 0) -> dict[str, float]:
    """Is A better than B? Pair on prompts, so shared difficulty cancels out."""
    y_true, pred_a, pred_b, groups = map(np.asarray, (y_true, pred_a, pred_b, groups))
    rng = np.random.default_rng(seed)
    uniq, inv = np.unique(groups, return_inverse=True)
    rows = [np.flatnonzero(inv == i) for i in range(len(uniq))]
    diffs = np.empty(n_boot)
    for b in range(n_boot):
        pick = np.concatenate([rows[i] for i in rng.integers(0, len(uniq), len(uniq))])
        diffs[b] = balanced_accuracy(y_true[pick], pred_a[pick]) - balanced_accuracy(
            y_true[pick], pred_b[pick])
    return {"mean_diff": float(diffs.mean()), "lo": float(np.quantile(diffs, 0.025)),
            "hi": float(np.quantile(diffs, 0.975)), "p_a_better": float((diffs > 0).mean())}


def leaderboard_noise(y_true, y_pred, groups, public_share: float = 0.4, n_sim: int = 500,
                      seed: int = 0) -> dict[str, float]:
    """How far apart could public and private scores land for the same predictions?

    Splits prompts into public/private at the competition's 40/60 ratio. If the true split is by
    row rather than by prompt the real gap will be smaller, so read this as an upper estimate.
    """
    y_true, y_pred, groups = map(np.asarray, (y_true, y_pred, groups))
    rng = np.random.default_rng(seed)
    uniq = np.unique(groups)
    gaps = np.empty(n_sim)
    for s in range(n_sim):
        public = rng.choice(uniq, size=int(round(public_share * len(uniq))), replace=False)
        mask = np.isin(groups, public)
        gaps[s] = balanced_accuracy(y_true[mask], y_pred[mask]) - balanced_accuracy(
            y_true[~mask], y_pred[~mask])
    return {"gap_sd": float(gaps.std(ddof=1)), "gap_p95_abs": float(np.quantile(np.abs(gaps), .95))}
