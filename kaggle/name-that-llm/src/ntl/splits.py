"""Cross-validation. Test prompts are unseen, so a prompt must never straddle a fold boundary."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold

from .data import LABEL, PROMPT


def grouped_folds(train: pd.DataFrame, n_splits: int = 5, seed: int = 42) -> np.ndarray:
    """Fold index per row, with whole prompts held out. This is the only scheme to trust."""
    y, groups = train[LABEL].to_numpy(), train[PROMPT].to_numpy()
    folds = np.full(len(train), -1, dtype=int)
    cv = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    for k, (_, val) in enumerate(cv.split(train, y, groups)):
        folds[val] = k
    assert_no_group_overlap(folds, groups)
    return folds


def random_folds(train: pd.DataFrame, n_splits: int = 5, seed: int = 42) -> np.ndarray:
    """Deliberately wrong scheme. Kept only so `ntl.cv --compare-random` can measure how wrong."""
    y = train[LABEL].to_numpy()
    folds = np.full(len(train), -1, dtype=int)
    cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    for k, (_, val) in enumerate(cv.split(train, y)):
        folds[val] = k
    return folds


def assert_no_group_overlap(folds: np.ndarray, groups: np.ndarray) -> None:
    frame = pd.DataFrame({"fold": folds, "group": groups})
    spread = frame.groupby("group")["fold"].nunique()
    if (spread > 1).any():
        raise AssertionError(f"{(spread > 1).sum()} prompts appear in more than one fold")
    if (folds < 0).any():
        raise AssertionError("some rows were never assigned to a fold")
