"""Checks to run before believing any CV score. Each returns a plain dict for the report."""
from __future__ import annotations

import re

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold, StratifiedKFold, cross_val_predict
from sklearn.neighbors import NearestNeighbors
from sklearn.pipeline import make_pipeline

from .assign import cluster_passages
from .data import ID, LABEL, PROMPT, TEXT, grid_report
from .features import mask_content_words

_NORM = re.compile(r"\W+")


def normalise(text: str) -> str:
    return _NORM.sub(" ", text.lower()).strip()


def duplicate_text(train: pd.DataFrame) -> dict:
    """Same passage under two labels is label noise; across prompts it breaks group isolation."""
    # Assign before filtering: on an empty frame, pandas would adopt the assigned Series' index.
    frame = train.assign(_n=train[TEXT].map(normalise))
    dup = frame[frame["_n"].duplicated(keep=False)]
    return {
        "duplicated_rows": len(dup),
        "conflicting_label_groups": int((dup.groupby("_n")[LABEL].nunique() > 1).sum()),
        "cross_prompt_groups": int((dup.groupby("_n")[PROMPT].nunique() > 1).sum()),
    }


def identity_mentions(train: pd.DataFrame, names: list[str] | None = None) -> dict:
    """Does a passage name its own model or lab? Free labels if so, and possibly absent in test."""
    tokens = set()
    for name in names if names is not None else train[LABEL].unique():
        tokens |= {t for t in re.split(r"[^a-z0-9]+", str(name).lower())
                   if len(t) >= 4 and not t.isdigit()}
    if not tokens:
        return {"tokens_checked": 0, "share_rows_with_token": 0.0}
    pattern = r"\b(?:" + "|".join(map(re.escape, sorted(tokens))) + r")\b"
    hits = train[TEXT].str.lower().str.contains(pattern, regex=True)
    return {"tokens_checked": len(tokens), "share_rows_with_token": float(hits.mean())}


def id_order_signal(train: pd.DataFrame, n_splits: int = 5) -> dict:
    """Can row order alone predict the label? Anything over chance means ids or file order leak."""
    y = train[LABEL].to_numpy()
    order = np.arange(len(train), dtype=float).reshape(-1, 1)
    numeric = train[ID].astype(str).str.extract(r"(\d+)$")[0].astype(float).fillna(0).to_numpy()
    X = np.column_stack([order, numeric])  # noqa: N806
    clf = HistGradientBoostingClassifier(max_iter=40)
    cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=0)
    acc = float((cross_val_predict(clf, X, y, cv=cv) == y).mean())
    return {"accuracy": acc, "chance": float(1 / train[LABEL].nunique())}


def length_signal(train: pd.DataFrame) -> dict:
    """Length alone should not separate models much; if it does, look at how passages were cut."""
    n = train[TEXT].str.split().str.len()
    by_model = n.groupby(train[LABEL]).mean()
    eta2 = ((by_model - n.mean()) ** 2 * train.groupby(LABEL).size()).sum() / ((n - n.mean()) ** 2).sum()
    return {"eta_squared": float(eta2), "min_model_mean": float(by_model.min()),
            "max_model_mean": float(by_model.max())}


def adversarial_validation(train: pd.DataFrame, test: pd.DataFrame) -> dict:
    """Train-vs-test classifier on content-masked text. Above about 0.6 means style differs.

    Masked, because test prompts are unseen by design and topic drift is expected. Passages from
    one prompt must also stay on one side of a split, or the model recognises test topics and AUC
    jumps to about 1 even when train and test come from the same source. Test has no prompt_id,
    so its groups are recovered by clustering.
    """
    both = pd.concat([train[TEXT], test[TEXT]], ignore_index=True).map(mask_content_words)
    y = np.r_[np.zeros(len(train)), np.ones(len(test))]
    test_groups = cluster_passages(test[TEXT].tolist(), max_size=train[LABEL].nunique())
    groups = np.r_[pd.factorize(train[PROMPT])[0], train[PROMPT].nunique() + test_groups]
    model = make_pipeline(
        TfidfVectorizer(analyzer="char", ngram_range=(1, 4), min_df=3, max_features=100_000,
                        sublinear_tf=True),
        LogisticRegression(C=1.0, max_iter=500, class_weight="balanced"),
    )
    prob = cross_val_predict(model, both.tolist(), y, cv=GroupKFold(5), groups=groups,
                             method="predict_proba")[:, 1]
    return {"auc": float(roc_auc_score(y, prob))}


def test_prompt_overlap(train: pd.DataFrame, test: pd.DataFrame) -> dict:
    """Are test prompts really unseen? Compares each test passage's nearest train neighbour with
    how close same-prompt pairs are inside train. Near-identical scores would mean overlap."""
    vec = TfidfVectorizer(min_df=1, sublinear_tf=True, stop_words="english")
    tr = vec.fit_transform(train[TEXT])
    te = vec.transform(test[TEXT])
    nn = NearestNeighbors(n_neighbors=2, metric="cosine").fit(tr)
    within = 1 - nn.kneighbors(tr)[0][:, 1]
    across = 1 - nn.kneighbors(te, n_neighbors=1)[0][:, 0]
    return {"train_within_nn_sim_median": float(np.median(within)),
            "test_to_train_nn_sim_median": float(np.median(across)),
            "looks_unseen": bool(np.median(across) < 0.75 * np.median(within))}


def cluster_shape(test: pd.DataFrame, n_models: int, threshold: float = 0.9) -> dict:
    """Does test look like a grid too? Clusters should pile up at exactly n_models passages."""
    sizes = np.bincount(cluster_passages(test[TEXT].tolist(), n_models, threshold))
    return {"n_clusters": len(sizes), "median_size": float(np.median(sizes)),
            "share_rows_in_full_clusters": float(sizes[sizes == n_models].sum() / sizes.sum())}


def run_all(train: pd.DataFrame, test: pd.DataFrame | None = None) -> dict:
    grid = grid_report(train)
    report: dict = {
        "grid": {**grid.__dict__, "is_grid": grid.is_grid},
        "duplicates": duplicate_text(train),
        "identity_mentions": identity_mentions(train),
        "id_order": id_order_signal(train),
        "length": length_signal(train),
    }
    if test is not None and len(test) >= 50:
        report["adversarial"] = adversarial_validation(train, test)
        report["test_prompt_overlap"] = test_prompt_overlap(train, test)
        report["test_cluster_shape"] = cluster_shape(test, train[LABEL].nunique())
    return report
