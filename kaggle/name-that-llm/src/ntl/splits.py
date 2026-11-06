"""Cross-validation. Test prompts are unseen, so a prompt must never straddle a fold boundary."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold
from sklearn.preprocessing import normalize

from .data import LABEL, PROMPT, TEXT


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


def topic_folds(df: pd.DataFrame, n_splits: int = 5, n_topics: int = 20,
                seed: int = 42) -> np.ndarray:
    """Harder than `grouped_folds`: whole topics are held out, not just individual prompts.

    Unseen prompts on a familiar subject are an easy kind of unseen. This clusters prompts by
    vocabulary, then keeps each cluster on one side of the split. Read the gap to grouped folds as
    a measure of how much the score leans on subjects being familiar. It is a stress test, not an
    estimate of the leaderboard.
    """
    docs = df.groupby(PROMPT)[TEXT].agg(" ".join)
    x = TfidfVectorizer(stop_words="english", sublinear_tf=True, min_df=2).fit_transform(docs)
    k = min(n_topics, len(docs) // 2)
    topics = KMeans(n_clusters=k, n_init=5, random_state=seed).fit_predict(normalize(x))
    fold_of_topic = {}
    sizes = np.zeros(n_splits, dtype=int)
    for topic, size in pd.Series(topics).value_counts().items():  # largest first, into emptiest fold
        fold_of_topic[topic] = int(sizes.argmin())
        sizes[fold_of_topic[topic]] += size
    by_prompt = pd.Series([fold_of_topic[t] for t in topics], index=docs.index)
    return df[PROMPT].map(by_prompt).to_numpy()
