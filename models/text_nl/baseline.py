"""TF-IDF + logistic regression: the model a transformer has to beat, and a label-noise probe."""

from __future__ import annotations

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline, make_pipeline


def make_baseline(seed: int = 0) -> Pipeline:
    return make_pipeline(
        TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True, max_features=500_000),
        LogisticRegression(C=10.0, max_iter=1000, random_state=seed),
    )


def logits(model: Pipeline, texts: list[str]) -> np.ndarray:
    margin = model.decision_function(texts)
    return np.column_stack([np.zeros_like(margin), margin])


def out_of_fold_probabilities(
    texts: list[str], labels: list[int], groups: np.ndarray, folds: int = 5, seed: int = 0
) -> np.ndarray:
    """P(positive) from models that never saw the text or any of its duplicates."""
    y = np.asarray(labels)
    out = np.zeros(len(y))
    splitter = StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=seed)
    documents = np.array(texts, dtype=object)
    for fit, held_out in splitter.split(documents, y, groups):
        model = make_baseline(seed).fit(documents[fit].tolist(), y[fit])
        out[held_out] = model.predict_proba(documents[held_out].tolist())[:, 1]
    return out


def suspicious_labels(
    texts: list[str], labels: list[int], probabilities: np.ndarray, top: int = 50
) -> list[dict]:
    """Examples whose label the out-of-fold model rejects most firmly.

    A *list for human review*, not an error rate: a confident disagreement can equally be a
    sarcastic review the baseline can't read.
    """
    y = np.asarray(labels)
    agreement = np.where(y == 1, probabilities, 1 - probabilities)
    worst = np.argsort(agreement)[:top]
    return [
        {"index": int(i), "label": int(y[i]), "p_label": float(agreement[i]),
         "text": texts[i][:300]}
        for i in worst
    ]
