"""One detector family, one dataset, several ways to split it.

The point is the gap between rows. `naive` is what a quick notebook reports.
`grouped` keeps templates and carriers apart. `leave-source-out` trains on some
publishers and tests on another, which is what meeting a new attack style is like.
The threshold always comes from validation data in the training sources.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from . import metrics as M
from .dataset import BARE_SHARE, Doc, build, naive_leak, split_groups, split_list
from .model import fit, fit_temperature, logits
from .sources import Benign, Payload, collect

# Same list as gauntlet's injection_filter, for a fair baseline.
REGEX = re.compile("|".join([
    r"ignore (all |any )?(the |your )?(previous|prior|above) (instructions|prompts)",
    r"disregard (all |any )?(the |your )?(previous|prior|above)",
    r"do not (tell|inform|mention|notify) (this to )?(the )?user",
    r"without (telling|informing|notifying) the user", r"new instructions?:", r"system prompt", r"you are now",
    r"<\s*(important|system|instructions?)\s*>"]), re.I)
TARGET_FPR = 0.01


def regex_scores(texts: list[str]) -> np.ndarray:
    return np.array([float(bool(REGEX.search(t))) for t in texts])


def score_block(y, s, groups, tau, prob=None) -> dict[str, Any]:
    out = {"auroc": M.auroc(y, s), **{k: v for k, v in M.rates(y, s, tau).items()}, "recall_at_1pct_fpr": M.recall_at_fpr(y, s, 0.01)}
    if prob is not None:
        out["ece"] = M.ece(y, prob)
    if len(np.unique(groups[y == 1])) > 2:
        out["auroc_ci"] = M.cluster_auc_ci(y, s, groups)
    return out


def run_fold(train: list[Doc], val: list[Doc], test: list[Doc], seed: int, cnn: bool = True) -> dict[str, Any]:
    ytr = [d.label for d in train]
    yv = np.array([d.label for d in val])
    yt = np.array([d.label for d in test])
    gt = np.array([d.group for d in test])
    tt, tv, tr = [d.text for d in test], [d.text for d in val], [d.text for d in train]
    res: dict[str, Any] = {"n_train": len(tr), "n_test": len(tt), "n_test_pos": int(yt.sum())}

    res["length"] = {"auroc": M.auroc(yt, np.array([len(t) for t in tt], float))}
    res["regex"] = score_block(yt, regex_scores(tt), gt, 0.5)

    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True, max_features=150_000)
    Xtr = vec.fit_transform(tr)
    lr = LogisticRegression(C=10, max_iter=300).fit(Xtr, ytr)
    sv, st = lr.decision_function(vec.transform(tv)), lr.decision_function(vec.transform(tt))
    res["tfidf_lr"] = score_block(yt, st, gt, M.threshold_at_fpr(sv[yv == 0], TARGET_FPR))

    if cnn:
        model = fit(tr, ytr, seed=seed)
        zv, zt = logits(model, tv), logits(model, tt)
        T = fit_temperature(zv, yv)
        res["byte_cnn"] = score_block(yt, zt, gt, M.threshold_at_fpr(zv[yv == 0], TARGET_FPR),
                                      prob=1 / (1 + np.exp(-zt / T)))
        res["byte_cnn"]["temperature"] = T
    return res


def naive_split(pos, neg, n, seed, bare_share=BARE_SHARE):
    rng = random.Random(seed)
    docs = build(pos, neg, n, rng, bare_share)
    k = int(len(docs) * 0.2)
    test, rest = docs[:k], docs[k:]
    v = int(len(rest) * 0.15)
    return rest[v:], rest[:v], test


def grouped_split(pos, neg, n, seed):
    rng = random.Random(seed)
    ptr, pte = split_groups(pos, 0.25, rng)
    ntr, nte = split_list(neg, 0.25, rng)
    ptr, pva = split_groups(ptr, 0.2, rng)
    ntr, nva = split_list(ntr, 0.2, rng)
    return build(ptr, ntr, n, rng), build(pva, nva, n // 5, rng), build(pte, nte, n // 3, rng, n_neg=min(len(nte), n // 3))


def source_out(pos, neg, p_out, n_out, n, seed):
    rng = random.Random(seed)
    ptr, pte = [p for p in pos if p.source != p_out], [p for p in pos if p.source == p_out]
    ntr, nte = [b for b in neg if b.source != n_out], [b for b in neg if b.source == n_out]
    ptr, pva = split_groups(ptr, 0.2, rng)
    ntr, nva = split_list(ntr, 0.2, rng)
    return build(ptr, ntr, n, rng), build(pva, nva, n // 5, rng), build(pte, nte, n // 3, rng, n_neg=min(len(nte), n // 3))


def audit(pos: list[Payload], neg: list[Benign], naive: tuple[list[Doc], list[Doc], list[Doc]]) -> dict[str, Any]:
    train, _, test = naive
    src = sorted({p.source for p in pos})
    return {
        "payloads": len(pos), "unique_payload_texts": len({p.text for p in pos}), "templates": len({p.group for p in pos}),
        "payloads_by_source": {s: sum(p.source == s for p in pos) for s in src},
        "templates_by_source": {s: len({p.group for p in pos if p.source == s}) for s in src},
        "benign_by_source": {s: sum(b.source == s for b in neg) for s in sorted({b.source for b in neg})},
        "regex_hits_on_benign_by_source": {s: float(regex_scores([b.text for b in neg if b.source == s]).mean())
                                           for s in sorted({b.source for b in neg})},
        "naive_split_leak": naive_leak(train, test),
    }


def mean_block(rows: list[dict[str, Any]], model: str) -> dict[str, float]:
    keys = ("auroc", "recall", "fpr", "recall_at_1pct_fpr", "ece")
    return {k: float(np.nanmean([r[model][k] for r in rows if k in r[model]])) for k in keys if any(k in r[model] for r in rows)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wheels", default="data/wheels")
    ap.add_argument("--n", type=int, default=1500, help="positive documents in a training set")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--out", default="reports/experiment.json")
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args(argv)
    torch.set_num_threads(2)
    pos, neg = collect(Path(a.wheels))
    t0 = time.time()
    n = 150 if a.smoke else a.n
    seeds = range(1 if a.smoke else a.seeds)
    res: dict[str, Any] = {"audit": audit(pos, neg, naive_split(pos, neg, n, 0)), "params": {"n": n, "seeds": len(seeds)},
                           "naive": [], "bare": [], "grouped": [], "leave_source_out": []}
    for s in seeds:
        res["naive"].append({"seed": s, **run_fold(*naive_split(pos, neg, n, s), s)})
        # Payloads alone versus documents, tested on payloads inside documents.
        tr, va, _ = naive_split(pos, neg, n, s, bare_share=1.0)
        _, _, te = grouped_split(pos, neg, n, s)
        res["bare"].append({"seed": s, **run_fold(tr, va, te, s)})
        res["grouped"].append({"seed": s, **run_fold(*grouped_split(pos, neg, n, s), s)})
        print(f"seed {s} done at {time.time() - t0:.0f}s", flush=True)
    psrc, nsrc = sorted({p.source for p in pos}), sorted({b.source for b in neg})
    for p in psrc:
        for b in nsrc:
            for s in seeds:
                fold = run_fold(*source_out(pos, neg, p, b, n, s), s)
                res["leave_source_out"].append({"pos_out": p, "neg_out": b, "seed": s, **fold})
            print(f"{p} / {b} done at {time.time() - t0:.0f}s", flush=True)
            Path(a.out).write_text(json.dumps(res, indent=1))
    Path(a.out).write_text(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
