"""Fit on all of train, predict test, write and validate submission.parquet.

Works locally and inside the Kaggle kernel. It writes a file; it never submits anything.

    python -m ntl.submit --data data/raw --out submission.parquet
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from .assign import assign_within_clusters, balance_classes, cluster_passages
from .cv import blend
from .data import ID, LABEL, TEXT, load
from .models import REGISTRY


def align(proba: np.ndarray, source: list[str], classes: np.ndarray) -> np.ndarray:
    """Reorder columns to `classes`, refusing a model trained on another label set."""
    if set(source) != set(classes):
        raise ValueError(f"label sets differ: {sorted(set(source) ^ set(classes))[:5]}")
    out = np.zeros_like(proba)
    out[:, np.searchsorted(classes, source)] = proba
    return out


def predict_test(train: pd.DataFrame, test: pd.DataFrame, names: list[str],
                 assign: bool = False, threshold: float = 0.9, balance: bool = False,
                 extra: tuple[np.ndarray, list[str]] | None = None,
                 extra_weight: float = 0.5) -> pd.DataFrame:
    """`extra` is (proba, classes) from `hf_train.predict_folds`. `extra_weight` is its share of the
    final blend, which should come from nested CV on OOF files, not from the leaderboard."""
    classes = np.array(sorted(train[LABEL].unique()))
    probas = []
    for name in names:
        model = REGISTRY[name]().fit(train[TEXT].tolist(), train[LABEL])
        col = np.searchsorted(classes, model.classes_)
        p = np.zeros((len(test), len(classes)))
        p[:, col] = model.predict_proba(test[TEXT].tolist())
        probas.append(p)
    proba = blend(probas) if len(probas) > 1 else probas[0]
    if extra is not None:
        proba = blend([proba, align(extra[0], extra[1], classes)],
                      weights=[1 - extra_weight, extra_weight])
    if balance:
        proba = balance_classes(proba)
    if assign:
        clusters = cluster_passages(test[TEXT].tolist(), len(classes), threshold)
        idx = assign_within_clusters(proba, clusters)
    else:
        idx = proba.argmax(axis=1)
    return pd.DataFrame({ID: test[ID].to_numpy(), LABEL: classes[idx]})


def validate_submission(sub: pd.DataFrame, test: pd.DataFrame, labels) -> None:
    """Everything Kaggle would reject, caught before a daily submission is wasted."""
    if list(sub.columns) != [ID, LABEL]:
        raise ValueError(f"columns must be [{ID}, {LABEL}], got {list(sub.columns)}")
    if sub.isna().any().any():
        raise ValueError("submission contains nulls")
    if sub[ID].duplicated().any():
        raise ValueError("duplicate ids")
    if set(sub[ID]) != set(test[ID]):
        raise ValueError("submission ids do not match test ids")
    unknown = set(sub[LABEL]) - set(labels)
    if unknown:
        raise ValueError(f"unknown labels: {sorted(unknown)[:5]}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default=None)
    ap.add_argument("--out", default="submission.parquet")
    ap.add_argument("--models", nargs="+", default=["tfidf_lr", "masked_lr"])
    ap.add_argument("--assign", action="store_true",
                    help="use within-prompt assignment; read NOTES.md first")
    ap.add_argument("--balance", action="store_true",
                    help="even out predicted class shares; assumes test is roughly balanced")
    ap.add_argument("--threshold", type=float, default=0.9,
                    help="clustering distance; use the value ntl.cv picked on real train")
    args = ap.parse_args()
    train, test = load(args.data)
    sub = predict_test(train, test, args.models, args.assign, args.threshold, args.balance)
    validate_submission(sub, test, train[LABEL].unique())
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    sub.to_parquet(args.out, index=False)
    print(f"wrote {args.out}: {len(sub)} rows")
    print(sub[LABEL].value_counts().describe().round(1).to_string())


if __name__ == "__main__":
    main()
