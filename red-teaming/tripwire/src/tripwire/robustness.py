"""How far does a detector's score travel when the spelling changes?

Trains on grouped splits, sets the threshold on clean validation data for 1% FPR, then
rewrites only the held-out payloads. Variants of each trained detector:

    plain       trained on clean text
    normalised  same training, text normalised before training and scoring
    canonical   normalised and case-folded, added after seeing the first results
    augmented   half the positives in training rewritten with the SEEN transforms

UNSEEN transforms are never used in training, so that row is the honest estimate of
meeting a rewrite nobody planned for. The same rewrites are applied to benign documents
to check that a variant has not just learned "odd characters mean attack".
"""

from __future__ import annotations

import argparse
import json
import random
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import torch
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from . import metrics as M
from .dataset import MAX_CHARS, Doc
from .evasion import SEEN, TRANSFORMS, UNSEEN, canon, normalise
from .experiment import REGEX, TARGET_FPR, grouped_split
from .model import fit, logits
from .sources import collect


def rewrite(doc: Doc, name: str, rng: random.Random) -> str:
    """Rewrite the payload in place, or the whole text if there is none or it was truncated."""
    new = TRANSFORMS[name]
    if doc.label and doc.payload and doc.payload in doc.text:
        return doc.text.replace(doc.payload, new(doc.payload, rng))[:MAX_CHARS * 4]
    return new(doc.text, rng)


def augment(train: list[Doc], rng: random.Random) -> list[Doc]:
    return [replace(d, text=rewrite(d, rng.choice(SEEN), rng)[:MAX_CHARS]) if d.label and rng.random() < 0.5 else d for d in train]


class Scorer:
    """Fits on texts, scores texts. `pre` is applied at both stages."""

    def __init__(self, kind: str, seed: int, pre=lambda t: t):
        self.kind, self.seed, self.pre = kind, seed, pre

    def fit(self, texts: list[str], y: list[int]) -> "Scorer":
        texts = [self.pre(t) for t in texts]
        if self.kind == "tfidf_lr":
            self.vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True, max_features=150_000)
            self.lr = LogisticRegression(C=10, max_iter=300).fit(self.vec.fit_transform(texts), y)
        else:
            self.model = fit(texts, y, seed=self.seed)
        return self

    def score(self, texts: list[str]) -> np.ndarray:
        texts = [self.pre(t) for t in texts]
        if self.kind == "tfidf_lr":
            return self.lr.decision_function(self.vec.transform(texts))
        return logits(self.model, texts)


def eval_variant(sc: Scorer, val: list[Doc], test: list[Doc], seed: int) -> dict[str, Any]:
    yv = np.array([d.label for d in val])
    tau = M.threshold_at_fpr(sc.score([d.text for d in val])[yv == 0], TARGET_FPR)
    pos = [d for d in test if d.label]
    neg = [d for d in test if not d.label]
    groups = np.array([d.group for d in pos])
    out: dict[str, Any] = {}
    for name in TRANSFORMS:
        rng = random.Random(seed)
        sp = sc.score([rewrite(d, name, rng)[:MAX_CHARS] for d in pos])
        sn = sc.score([rewrite(d, name, rng)[:MAX_CHARS] for d in neg])
        out[name] = {"recall": float((sp >= tau).mean()), "fpr": float((sn >= tau).mean()),
                     "group_recall": [float((sp[groups == g] >= tau).mean()) for g in np.unique(groups)],
                     "groups": [[str(g), int((sp[groups == g] >= tau).sum()), int((groups == g).sum())] for g in np.unique(groups)]}
    return out


def regex_row(test: list[Doc], seed: int, pre=lambda t: t) -> dict[str, Any]:
    pos = [d for d in test if d.label]
    neg = [d for d in test if not d.label]
    groups = np.array([d.group for d in pos])
    hit = lambda ts: np.array([bool(REGEX.search(pre(t))) for t in ts])  # noqa: E731
    out = {}
    for name in TRANSFORMS:
        rng = random.Random(seed)
        p = hit([rewrite(d, name, rng)[:MAX_CHARS] for d in pos])
        n = hit([rewrite(d, name, rng)[:MAX_CHARS] for d in neg])
        out[name] = {"recall": float(p.mean()), "fpr": float(n.mean()),
                     "group_recall": [float(p[groups == g].mean()) for g in np.unique(groups)],
                     "groups": [[str(g), int(p[groups == g].sum()), int((groups == g).sum())] for g in np.unique(groups)]}
    return out


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Mean over seeds, with a bootstrap over held-out templates pooled across seeds."""
    rng = np.random.default_rng(0)
    out: dict[str, Any] = {}
    for name in TRANSFORMS:
        g = np.array([x for r in rows for x in r[name]["group_recall"]])
        boot = [rng.choice(g, len(g)).mean() for _ in range(2000)]
        out[name] = {"recall": float(np.mean([r[name]["recall"] for r in rows])), "fpr": float(np.mean([r[name]["fpr"] for r in rows])),
                     "template_mean_recall": float(g.mean()), "template_ci": [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))]}
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wheels", default="data/wheels")
    ap.add_argument("--n", type=int, default=1500)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--out", default="reports/robustness.json")
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args(argv)
    torch.set_num_threads(2)
    pos, neg = collect(Path(a.wheels))
    n = 150 if a.smoke else a.n
    seeds = range(1 if a.smoke else a.seeds)
    rows: dict[str, list[dict[str, Any]]] = {}
    t0 = time.time()
    for s in seeds:
        tr, va, te = grouped_split(pos, neg, n, s)
        y, texts = [d.label for d in tr], [d.text for d in tr]
        aug = augment(tr, random.Random(s))
        rows.setdefault("regex/plain", []).append(regex_row(te, s))
        rows.setdefault("regex/normalised", []).append(regex_row(te, s, normalise))
        for kind in ("tfidf_lr", "byte_cnn"):
            for label, sc, xs in (("plain", Scorer(kind, s), texts), ("normalised", Scorer(kind, s, normalise), texts),
                                  ("canonical", Scorer(kind, s, canon), texts),
                                  ("augmented", Scorer(kind, s), [d.text for d in aug]),
                                  ("augmented+normalised", Scorer(kind, s, normalise), [d.text for d in aug])):
                rows.setdefault(f"{kind}/{label}", []).append(eval_variant(sc.fit(xs, y), va, te, s))
        print(f"seed {s} done at {time.time() - t0:.0f}s", flush=True)
    res = {"params": {"n": n, "seeds": len(seeds), "target_fpr": TARGET_FPR, "seen": SEEN, "unseen": UNSEEN},
           "summary": {k: summarise(v) for k, v in rows.items()}}
    Path(a.out).write_text(json.dumps(res, indent=1))
    long = [[key, s, name, *g] for key, seeds_ in rows.items() for s, r in enumerate(seeds_) for name in TRANSFORMS for g in r[name]["groups"]]
    Path(a.out).with_name("robustness_groups.json").write_text(json.dumps(
        {"columns": ["model", "seed", "transform", "template", "caught", "n"], "rows": long}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
