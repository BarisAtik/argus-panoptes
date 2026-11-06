"""Grouped cross-validation for every candidate; writes OOF predictions and a metrics file.

    python -m ntl.cv --data data/synth --out artifacts/synth --models tfidf_lr masked_lr style_lr
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.metrics import adjusted_rand_score

from .assign import (
    assign_within_clusters,
    cluster_passages,
    stress_curve,
    tune_threshold,
)
from .data import ID, LABEL, PROMPT, TEXT, load
from .leakage import run_all
from .metrics import (
    balanced_accuracy,
    leaderboard_noise,
    paired_prompt_bootstrap,
    prompt_bootstrap_ci,
)
from .models import REGISTRY
from .splits import grouped_folds, random_folds, topic_folds


def oof_proba(model, train: pd.DataFrame, folds: np.ndarray, classes: np.ndarray) -> np.ndarray:
    """Out-of-fold probabilities, aligned to `classes` whatever each fold happened to contain."""
    proba = np.zeros((len(train), len(classes)))
    for k in np.unique(folds):
        fit, val = folds != k, folds == k
        m = clone(model).fit(train.loc[fit, TEXT].tolist(), train.loc[fit, LABEL])
        col = np.searchsorted(classes, m.classes_)
        proba[np.ix_(val, col)] = m.predict_proba(train.loc[val, TEXT].tolist())
    return proba


def blend(probas: list[np.ndarray], weights=None) -> np.ndarray:
    """Geometric mean; a model that is sure a label is wrong gets a veto.

    Set `weights` in advance or by nested CV. Fitting them on the OOF they are scored on inflates it.
    """
    log = np.average([np.log(np.clip(p, 1e-9, 1)) for p in probas], axis=0, weights=weights)
    p = np.exp(log)
    return p / p.sum(axis=1, keepdims=True)


def assignment_gain(train: pd.DataFrame, folds: np.ndarray, proba: np.ndarray,
                    classes: np.ndarray, cap: int) -> dict:
    """Simulate test: per fold, hide prompt ids, cluster on text, assign within clusters.

    The threshold is tuned on all of train at once because a fold is much smaller than test, and
    density changes what a good threshold is. Each fold is then clustered with that threshold.
    """
    y = train[LABEL].to_numpy()
    y_idx = np.searchsorted(classes, y)
    pred = proba.argmax(axis=1)
    curve = tune_threshold(train[TEXT].tolist(), train[PROMPT].to_numpy(), cap)
    threshold = max(curve, key=curve.get)
    clusters = np.zeros(len(train), dtype=int)
    aris = []
    offset = 0
    for k in np.unique(folds):
        val = np.flatnonzero(folds == k)
        c = cluster_passages(train.loc[val, TEXT].tolist(), cap, threshold)
        aris.append(adjusted_rand_score(train.loc[val, PROMPT], c))
        clusters[val] = c + offset
        offset += c.max() + 1
    assigned = assign_within_clusters(proba, clusters)
    oracle = assign_within_clusters(proba, pd.factorize(train[PROMPT])[0])
    return {
        "threshold": threshold,
        "threshold_curve": curve,
        "argmax": balanced_accuracy(y, classes[pred]),
        "assigned_with_clusters": balanced_accuracy(y, classes[assigned]),
        "assigned_with_true_prompts_oracle": balanced_accuracy(y, classes[oracle]),
        "cluster_ari": float(np.mean(aris)),
        "n_clusters": int(offset),
        "paired_vs_argmax": paired_prompt_bootstrap(
            y, classes[assigned], classes[pred], train[PROMPT], n_boot=300),
        "stress": stress_curve(proba, y_idx, train[PROMPT].to_numpy()),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default=None)
    ap.add_argument("--out", default="artifacts/cv")
    ap.add_argument("--models", nargs="+", default=["tfidf_lr", "masked_lr", "style_lr"])
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--compare-random", action="store_true",
                    help="also score the first model under (wrong) random folds")
    ap.add_argument("--topic-folds", action="store_true",
                    help="also score the first model with whole topics held out")
    ap.add_argument("--no-leakage", action="store_true", help="skip the slower leakage report")
    args = ap.parse_args()

    train, test = load(args.data)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    classes = np.array(sorted(train[LABEL].unique()))
    y, groups = train[LABEL].to_numpy(), train[PROMPT].to_numpy()
    folds = grouped_folds(train, args.folds, args.seed)
    results: dict = {"n_rows": len(train), "folds": args.folds}

    if not args.no_leakage:
        results["leakage"] = run_all(train, test)
        print(json.dumps(results["leakage"], indent=2, default=float))

    probas: dict[str, np.ndarray] = {}
    for name in args.models:
        probas[name] = oof_proba(REGISTRY[name](), train, folds, classes)
    if len(probas) > 1:
        probas["blend"] = blend(list(probas.values()))

    rows = []
    for name, p in probas.items():
        pred = classes[p.argmax(axis=1)]
        ci = prompt_bootstrap_ci(y, pred, groups)
        rows.append({"model": name, **ci})
        frame = pd.DataFrame(p, columns=classes)
        frame.insert(0, ID, train[ID].to_numpy())
        frame.insert(1, "fold", folds)
        frame.insert(2, LABEL, y)
        frame.insert(3, PROMPT, groups)
        frame.to_parquet(out / f"oof_{name}.parquet", index=False)
    table = pd.DataFrame(rows).sort_values("point", ascending=False)
    results["scores"] = table.to_dict("records")
    print(table.round(4).to_string(index=False))

    best = table.iloc[0]["model"]
    best_pred = classes[probas[best].argmax(axis=1)]
    results["best"] = best
    results["leaderboard_noise"] = leaderboard_noise(y, best_pred, groups)
    results["assignment"] = assignment_gain(train, folds, probas[best], classes,
                                            cap=len(classes))
    print(json.dumps({"lb_noise": results["leaderboard_noise"],
                      "assignment": results["assignment"]}, indent=2))

    if args.compare_random:
        first = args.models[0]
        rnd = random_folds(train, args.folds, args.seed)
        p = oof_proba(REGISTRY[first](), train, rnd, classes)
        results["random_vs_grouped"] = {
            "model": first,
            "random_kfold": balanced_accuracy(y, classes[p.argmax(axis=1)]),
            "grouped": balanced_accuracy(y, classes[probas[first].argmax(axis=1)]),
        }
        print(json.dumps(results["random_vs_grouped"], indent=2))

    if args.topic_folds:
        first = args.models[0]
        p = oof_proba(REGISTRY[first](), train, topic_folds(train, args.folds), classes)
        results["topic_held_out"] = {
            "model": first,
            "topic_held_out": balanced_accuracy(y, classes[p.argmax(axis=1)]),
            "grouped": balanced_accuracy(y, classes[probas[first].argmax(axis=1)]),
        }
        print(json.dumps(results["topic_held_out"], indent=2))

    (out / "metrics.json").write_text(json.dumps(results, indent=2, default=float))


if __name__ == "__main__":
    main()
