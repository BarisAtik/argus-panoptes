"""Validation experiments on the real-text proxy. Each writes reports/proxy/<name>.json.

    python -m ntl.proxy_experiments honesty models genre curve assign shift balance \
        selection alarm

The questions are about method, not about the competition's score:

    honesty   Does grouped CV predict a locked holdout better than random CV? Do its CIs cover it?
    models    Which candidates beat plain TF-IDF on unseen prompts, chosen on OOF, checked on holdout?
    genre     How much does a score fall when test prompts come from another genre?
    curve     How much would extra training prompts be worth?
    assign    Does within-prompt assignment help with real clustering on real text?
    shift     Which unlabelled corrections survive a change of genre?
    balance   Does forcing even class shares help, and what if the shares are not even?
    selection Does OOF pick the right blend across resampled splits?
    alarm     Would adversarial validation or topic-held-out folds have warned about shift?
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import adjusted_rand_score, log_loss
from sklearn.preprocessing import StandardScaler

from .assign import assign_within_clusters, balance_classes, cluster_passages, tune_threshold
from .cv import blend, oof_proba
from .data import LABEL, PROMPT, TEXT
from .features import StyleFeatures
from .leakage import adversarial_validation
from .metrics import balanced_accuracy, paired_prompt_bootstrap, prompt_bootstrap_ci
from .models import REGISTRY
from .proxy import FAMILY, make_split, read_grid
from .splits import grouped_folds, random_folds, topic_folds


def holdout_proba(name: str, train: pd.DataFrame, test: pd.DataFrame,
                  classes: np.ndarray) -> np.ndarray:
    model = REGISTRY[name]().fit(train[TEXT].tolist(), train[LABEL])
    p = np.zeros((len(test), len(classes)))
    p[:, np.searchsorted(classes, model.classes_)] = model.predict_proba(test[TEXT].tolist())
    return p


def score(y, proba, classes) -> float:
    return balanced_accuracy(y, classes[proba.argmax(axis=1)])


def honesty(grid: pd.DataFrame, seeds: int = 10) -> dict:
    rows = []
    for seed in range(seeds):
        train, test = make_split(grid, 150, 220, seed)
        classes = np.array(sorted(train[LABEL].unique()))
        y = train[LABEL].to_numpy()
        model = REGISTRY["tfidf_lr"]()
        grouped = oof_proba(model, train, grouped_folds(train, 5, 42), classes)
        rand = oof_proba(model, train, random_folds(train, 5, 42), classes)
        ci = prompt_bootstrap_ci(y, classes[grouped.argmax(axis=1)], train[PROMPT], n_boot=300)
        hold = holdout_proba("tfidf_lr", train, test, classes)
        pred = classes[hold.argmax(axis=1)]
        hold_ci = prompt_bootstrap_ci(test[LABEL], pred, test[PROMPT], n_boot=300)
        rows.append({"seed": seed, "grouped": ci["point"], "grouped_lo": ci["lo"],
                     "grouped_hi": ci["hi"], "grouped_se": ci["se"],
                     "random": score(y, rand, classes), "holdout": hold_ci["point"],
                     "holdout_se": hold_ci["se"]})
        print(rows[-1], flush=True)
    frame = pd.DataFrame(rows)
    gap = frame["holdout"] - frame["grouped"]
    joint_se = np.sqrt(frame["grouped_se"] ** 2 + frame["holdout_se"] ** 2)
    return {
        "runs": rows,
        "mean_grouped": frame["grouped"].mean(),
        "mean_random": frame["random"].mean(),
        "mean_holdout": frame["holdout"].mean(),
        "mean_gap_holdout_minus_grouped": gap.mean(),
        "sd_gap": gap.std(ddof=1),
        "mae_grouped": gap.abs().mean(),
        "mae_random": (frame["holdout"] - frame["random"]).abs().mean(),
        "ci_covers_holdout": float(((frame["holdout"] >= frame["grouped_lo"])
                                    & (frame["holdout"] <= frame["grouped_hi"])).mean()),
        "predictive_interval_covers_holdout": float((gap.abs() <= 1.96 * joint_se).mean()),
    }


def hierarchical_proba(train: pd.DataFrame, test_texts: list[str], classes: np.ndarray,
                       family: dict[str, str], base: str = "tfidf_lr") -> np.ndarray:
    """P(author) = P(family) * P(author | family). Each step gets its own model."""
    fam = train[LABEL].map(family)
    top = REGISTRY[base]().fit(train[TEXT].tolist(), fam)
    p_fam = top.predict_proba(test_texts)
    out = np.zeros((len(test_texts), len(classes)))
    for j, f in enumerate(top.classes_):
        members = sorted(a for a in classes if family[a] == f)
        cols = np.searchsorted(classes, members)
        if len(members) == 1:
            out[:, cols[0]] = p_fam[:, j]
            continue
        sub = train[fam == f]
        inner = REGISTRY[base]().fit(sub[TEXT].tolist(), sub[LABEL])
        out[np.ix_(np.arange(len(test_texts)), np.searchsorted(classes, inner.classes_))] = (
            p_fam[:, [j]] * inner.predict_proba(test_texts))
    return out


def models_exp(grid: pd.DataFrame, seed: int = 0) -> dict:
    train, test = make_split(grid, 150, 220, seed)
    classes = np.array(sorted(train[LABEL].unique()))
    folds = grouped_folds(train, 5, 42)
    y, groups = train[LABEL].to_numpy(), train[PROMPT].to_numpy()
    y_test = test[LABEL].to_numpy()
    names = ["tfidf_lr", "tfidf_lr_c100", "word_lr", "char_lr", "nb_lr", "masked_lr", "style_lr",
             "style_gbm"]
    oof, hold = {}, {}
    for name in names:
        oof[name] = oof_proba(REGISTRY[name](), train, folds, classes)
        hold[name] = holdout_proba(name, train, test, classes)
        print(name, score(y, oof[name], classes), score(y_test, hold[name], classes), flush=True)

    hier_oof = np.zeros_like(oof["tfidf_lr"])
    for k in np.unique(folds):
        val = folds == k
        hier_oof[val] = hierarchical_proba(train[~val], train.loc[val, TEXT].tolist(), classes,
                                           FAMILY)
    oof["hierarchical"] = hier_oof
    hold["hierarchical"] = hierarchical_proba(train, test[TEXT].tolist(), classes, FAMILY)

    pairs = {"blend_tfidf_masked": ["tfidf_lr", "masked_lr"],
             "blend_all_three": ["tfidf_lr", "masked_lr", "style_lr"],
             "blend_tfidf_nb": ["tfidf_lr", "nb_lr"]}
    for label, members in pairs.items():
        oof[label] = blend([oof[m] for m in members])
        hold[label] = blend([hold[m] for m in members])

    base = classes[hold["tfidf_lr"].argmax(axis=1)]
    rows = []
    for name in oof:
        pred = classes[hold[name].argmax(axis=1)]
        paired = paired_prompt_bootstrap(y_test, pred, base, test[PROMPT], n_boot=500)
        rows.append({
            "model": name,
            "oof": score(y, oof[name], classes),
            "oof_log_loss": log_loss(y, np.clip(oof[name], 1e-9, 1), labels=classes),
            "holdout": score(y_test, hold[name], classes),
            "holdout_family_acc": float(np.mean(
                pd.Series(y_test).map(FAMILY).to_numpy() == pd.Series(pred).map(FAMILY).to_numpy())),
            "holdout_diff_vs_tfidf": paired["mean_diff"],
            "diff_lo": paired["lo"], "diff_hi": paired["hi"],
        })
    table = pd.DataFrame(rows).sort_values("oof", ascending=False)
    print(table.round(3).to_string(index=False))
    pick = table.iloc[0]["model"]
    return {"table": table.to_dict("records"), "picked_on_oof": pick,
            "n_train_rows": len(train), "groups": int(pd.Series(groups).nunique())}


def genre_exp(grid: pd.DataFrame, seeds: int = 3) -> dict:
    """Train on one genre, test on unseen prompts from the same genre and from the other one."""
    rows = []
    for seed in range(seeds):
        for src, dst in (("wp", "essay"), ("essay", "wp")):
            train, same = make_split(grid[grid["genre"] == src], 150, 220, seed)
            _, other = make_split(grid[grid["genre"] == dst], 150, 220, seed)
            classes = np.array(sorted(train[LABEL].unique()))
            for name in ("tfidf_lr", "masked_lr", "style_lr"):
                model = REGISTRY[name]().fit(train[TEXT].tolist(), train[LABEL])
                cv = oof_proba(model, train, grouped_folds(train, 5, 42), classes)
                row = {"seed": seed, "train": src, "model": name,
                       "grouped_cv": score(train[LABEL], cv, classes),
                       "same_genre": balanced_accuracy(same[LABEL],
                                                       model.predict(same[TEXT].tolist())),
                       "other_genre": balanced_accuracy(other[LABEL],
                                                        model.predict(other[TEXT].tolist()))}
                rows.append(row)
                print(row, flush=True)
    frame = pd.DataFrame(rows)
    return {"runs": rows, "summary": frame.groupby(["train", "model"])[
        ["grouped_cv", "same_genre", "other_genre"]].mean().reset_index().to_dict("records")}


def curve_exp(grid: pd.DataFrame, sizes=(38, 75, 150, 300, 600, 1200)) -> dict:
    rows = []
    for seed in range(2):
        pool_train, test = make_split(grid, 1200, 400, seed)
        order = pool_train[PROMPT].drop_duplicates().to_numpy()
        for n in sizes:
            if n == 1200 and seed:
                continue
            sub = pool_train[pool_train[PROMPT].isin(order[:n])]
            classes = np.array(sorted(sub[LABEL].unique()))
            p = holdout_proba("tfidf_lr", sub, test, classes)
            rows.append({"seed": seed, "train_prompts": n, "rows": len(sub),
                         "holdout": score(test[LABEL], p, classes)})
            print(rows[-1], flush=True)
    return {"runs": rows, "n_classes": 7}


def assign_exp(grid: pd.DataFrame, seeds: int = 3) -> dict:
    """The real test: cluster the holdout, then assign, and compare with what was predicted."""
    rows = []
    for seed in range(seeds):
        train, test = make_split(grid, 150, 220, seed)
        classes = np.array(sorted(train[LABEL].unique()))
        cap = len(classes)
        p = holdout_proba("tfidf_lr", train, test, classes)
        y = test[LABEL].to_numpy()
        base = classes[p.argmax(axis=1)]
        curve = tune_threshold(train[TEXT].tolist(), train[PROMPT].to_numpy(), cap)
        threshold = max(curve, key=curve.get)
        clusters = cluster_passages(test[TEXT].tolist(), cap, threshold)
        sizes = np.bincount(clusters)
        oracle = assign_within_clusters(p, pd.factorize(test[PROMPT])[0])
        loose = assign_within_clusters(p, clusters)
        strict = assign_within_clusters(p, clusters, min_size=cap)
        row = {
            "seed": seed, "threshold": threshold, "train_ari": curve[threshold],
            "test_ari": float(adjusted_rand_score(test[PROMPT], clusters)),
            "share_rows_in_full_clusters": float(sizes[sizes == cap].sum() / sizes.sum()),
            "argmax": balanced_accuracy(y, base),
            "all_clusters": balanced_accuracy(y, classes[loose]),
            "full_clusters_only": balanced_accuracy(y, classes[strict]),
            "oracle_prompts": balanced_accuracy(y, classes[oracle]),
            "all_vs_argmax": paired_prompt_bootstrap(y, classes[loose], base, test[PROMPT],
                                                     n_boot=300),
            "full_vs_argmax": paired_prompt_bootstrap(y, classes[strict], base, test[PROMPT],
                                                      n_boot=300),
        }
        rows.append(row)
        print(row, flush=True)
    return {"runs": rows}


def style_with_test_scaling(train: pd.DataFrame, test: pd.DataFrame,
                            classes: np.ndarray) -> np.ndarray:
    """Style model where test is scaled by its own mean and SD, which removes a uniform shift."""
    features = StyleFeatures()
    x_train = StandardScaler().fit_transform(features.transform(train[TEXT].tolist()))
    x_test = StandardScaler().fit_transform(features.transform(test[TEXT].tolist()))
    model = LogisticRegression(C=1.0, max_iter=2000, class_weight="balanced")
    model.fit(x_train, train[LABEL])
    p = np.zeros((len(test), len(classes)))
    p[:, np.searchsorted(classes, model.classes_)] = model.predict_proba(x_test)
    return p


def shift_exp(grid: pd.DataFrame, seeds: int = 3) -> dict:
    """Unlabelled corrections for shift. These change nothing in training, so they are cheap."""
    rows = []
    for seed in range(seeds):
        for src, dst in (("wp", "essay"), ("essay", "wp")):
            train, same = make_split(grid[grid["genre"] == src], 150, 220, seed)
            _, other = make_split(grid[grid["genre"] == dst], 150, 220, seed)
            classes = np.array(sorted(train[LABEL].unique()))
            for where, test in (("same", same), ("other", other)):
                y = test[LABEL].to_numpy()
                tfidf = holdout_proba("tfidf_lr", train, test, classes)
                masked = holdout_proba("masked_lr", train, test, classes)
                style = holdout_proba("style_lr", train, test, classes)
                scaled = style_with_test_scaling(train, test, classes)
                views = {"tfidf": tfidf, "tfidf_balanced": balance_classes(tfidf),
                         "masked": masked, "masked_balanced": balance_classes(masked),
                         "style": style, "style_test_scaled": scaled,
                         "style_scaled_balanced": balance_classes(scaled),
                         "blend_balanced": balance_classes(blend([tfidf, masked, scaled]))}
                row = {"seed": seed, "train": src, "test": where}
                row |= {k: score(y, v, classes) for k, v in views.items()}
                rows.append(row)
                print(row, flush=True)
    frame = pd.DataFrame(rows)
    summary = frame.drop(columns=["seed"]).groupby(["train", "test"]).mean().reset_index()
    return {"runs": rows, "summary": summary.to_dict("records")}


def balance_exp(grid: pd.DataFrame, seeds: int = 5) -> dict:
    """The mixed-genre competition-sized split: does balancing help, and does it stack with
    assignment? Includes a test with one class share deliberately wrong."""
    rows = []
    for seed in range(seeds):
        train, test = make_split(grid, 150, 220, seed)
        classes = np.array(sorted(train[LABEL].unique()))
        p = holdout_proba("tfidf_lr", train, test, classes)
        y = test[LABEL].to_numpy()
        balanced = balance_classes(p)
        oracle = pd.factorize(test[PROMPT])[0]
        paired = paired_prompt_bootstrap(y, classes[balanced.argmax(axis=1)],
                                         classes[p.argmax(axis=1)], test[PROMPT], n_boot=300)
        skew = test[(test[LABEL] != "human") | (test["num"] % 3 == 0)]
        p_skew = holdout_proba("tfidf_lr", train, skew, classes)
        rows.append({
            "seed": seed, "argmax": score(y, p, classes), "balanced": score(y, balanced, classes),
            "diff_lo": paired["lo"], "diff_hi": paired["hi"],
            "oracle_assign": balanced_accuracy(y, classes[assign_within_clusters(p, oracle)]),
            "skewed_test_argmax": score(skew[LABEL], p_skew, classes),
            "skewed_test_balanced": score(skew[LABEL], balance_classes(p_skew), classes),
        })
        print(rows[-1], flush=True)
    return {"runs": rows, "mean": pd.DataFrame(rows).drop(columns="seed").mean().to_dict()}


def selection_exp(grid: pd.DataFrame, seeds: int = 6) -> dict:
    """On seed 0 the blend looked worst on OOF and best on holdout. Is that a pattern or luck?"""
    names = ["tfidf_lr", "masked_lr", "style_lr"]
    combos = {"tfidf": names[:1], "tfidf+masked": names[:2], "all_three": names}
    rows = []
    for seed in range(seeds):
        train, test = make_split(grid, 150, 220, seed)
        classes = np.array(sorted(train[LABEL].unique()))
        folds = grouped_folds(train, 5, 42)
        oof = {n: oof_proba(REGISTRY[n](), train, folds, classes) for n in names}
        hold = {n: holdout_proba(n, train, test, classes) for n in names}
        for label, members in combos.items():
            o = blend([oof[m] for m in members]) if len(members) > 1 else oof[members[0]]
            h = blend([hold[m] for m in members]) if len(members) > 1 else hold[members[0]]
            rows.append({"seed": seed, "candidate": label, "oof": score(train[LABEL], o, classes),
                         "holdout": score(test[LABEL], h, classes),
                         "holdout_balanced": score(test[LABEL], balance_classes(h), classes)})
        print(rows[-3:], flush=True)
    frame = pd.DataFrame(rows)
    wide = frame.pivot(index="seed", columns="candidate", values="oof")
    picks = wide.idxmax(axis=1)
    held = frame.set_index(["seed", "candidate"])["holdout"]
    regret = [held[(s, held.loc[s].idxmax())] - held[(s, c)] for s, c in picks.items()]
    return {"runs": rows, "mean": frame.drop(columns="seed").groupby("candidate").mean()
            .reset_index().to_dict("records"), "oof_pick_by_seed": picks.to_dict(),
            "mean_regret_of_oof_pick": float(np.mean(regret))}


def alarm_exp(grid: pd.DataFrame, seeds: int = 3) -> dict:
    """Would we have been warned? Two checks that need no labels from the shifted data."""
    rows = []
    for seed in range(seeds):
        for src, dst in (("wp", "essay"), ("essay", "wp")):
            train, same = make_split(grid[grid["genre"] == src], 150, 220, seed)
            _, other = make_split(grid[grid["genre"] == dst], 150, 220, seed)
            rows.append({"seed": seed, "train": src,
                         "auc_same_genre": adversarial_validation(train, same)["auc"],
                         "auc_other_genre": adversarial_validation(train, other)["auc"]})
            print(rows[-1], flush=True)
        mixed, _ = make_split(grid, 150, 220, seed)
        classes = np.array(sorted(mixed[LABEL].unique()))
        model = REGISTRY["tfidf_lr"]()
        y = mixed[LABEL]
        rows.append({"seed": seed, "train": "mixed",
                     "grouped": score(y, oof_proba(model, mixed, grouped_folds(mixed), classes),
                                      classes),
                     "topic_held_out": score(y, oof_proba(model, mixed, topic_folds(mixed),
                                                          classes), classes)})
        print(rows[-1], flush=True)
    return {"runs": rows}


EXPERIMENTS = {"honesty": honesty, "models": models_exp, "genre": genre_exp, "curve": curve_exp,
               "assign": assign_exp, "shift": shift_exp, "balance": balance_exp,
               "selection": selection_exp, "alarm": alarm_exp}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="+", choices=sorted(EXPERIMENTS))
    ap.add_argument("--cache", type=Path, default=Path("data/proxy/cache"))
    ap.add_argument("--out", type=Path, default=Path("reports/proxy"))
    args = ap.parse_args()
    grid = read_grid(args.cache)
    args.out.mkdir(parents=True, exist_ok=True)
    for name in args.names:
        result = EXPERIMENTS[name](grid)
        (args.out / f"{name}.json").write_text(json.dumps(result, indent=1, default=float))


if __name__ == "__main__":
    main()
