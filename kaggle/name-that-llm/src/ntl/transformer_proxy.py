"""Does a real pretrained transformer beat the sparse models on unseen prompts?

Runs on the Ghostbuster proxy with RoBERTa rebuilt by `ntl.local_roberta`. Plan and predictions are
in reports/proxy/transformer_plan.md, written before any result existed.

    python -m ntl.transformer_proxy holdout --model artifacts/roberta-base-spacy --seeds 100 101
    python -m ntl.transformer_proxy genre --model artifacts/roberta-base-spacy --seeds 100
    python -m ntl.transformer_proxy cv --model artifacts/roberta-base-spacy --seeds 100

Each finished fit is saved under artifacts/transformer, and a rerun skips it, so a stopped run
loses at most one fit. About an hour per fit on 2 CPUs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from transformers import AutoModel, AutoModelForSequenceClassification, AutoTokenizer

from .cv import blend
from .data import LABEL, PROMPT, TEXT
from .hf_train import batches, train_one
from .metrics import balanced_accuracy, paired_prompt_bootstrap
from .proxy import FAMILY, make_split, read_grid
from .proxy_experiments import holdout_proba, score
from .splits import grouped_folds

SETTINGS = {"epochs": 3, "batch_size": 8, "max_length": 192, "lr": 2e-5, "label_smoothing": 0.05}
SPARSE = ("tfidf_lr", "masked_lr")


def _args() -> argparse.Namespace:
    return argparse.Namespace(**SETTINGS)


@torch.no_grad()
def embed(path: str, tokenizer, texts: list[str]) -> np.ndarray:
    """Mean of the last hidden state, with no training: how much do stock features already give?"""
    model = AutoModel.from_pretrained(path, add_pooling_layer=False).eval()
    order = np.argsort([len(t) for t in texts])
    loader = batches(tokenizer, [texts[i] for i in order], None, 16, SETTINGS["max_length"], False)
    parts = []
    for batch, _ in loader:
        hidden = model(**batch).last_hidden_state
        mask = batch["attention_mask"].unsqueeze(-1)
        parts.append(((hidden * mask).sum(1) / mask.sum(1)).numpy())
    done = np.concatenate(parts)
    out = np.empty_like(done)
    out[order] = done
    return out


def frozen_proba(path, tokenizer, train, tests: list[pd.DataFrame], classes) -> list[np.ndarray]:
    x = embed(path, tokenizer, train[TEXT].tolist())
    scaler = StandardScaler().fit(x)
    clf = LogisticRegression(C=0.01, max_iter=2000, class_weight="balanced")
    clf.fit(scaler.transform(x), train[LABEL])
    return [clf.predict_proba(scaler.transform(embed(path, tokenizer, t[TEXT].tolist())))
            for t in tests]


def tuned_proba(path, tokenizer, train, tests: list[pd.DataFrame], classes) -> list[np.ndarray]:
    """One fit, predictions for every test frame. Seeded, so a rerun matches."""
    torch.manual_seed(0)
    y = np.searchsorted(classes, train[LABEL].to_numpy())
    model = AutoModelForSequenceClassification.from_pretrained(path, num_labels=len(classes))
    args = _args()
    joined = pd.concat(tests)[TEXT].tolist()
    both = train_one(model, tokenizer, train[TEXT].tolist(), y, joined, args, "cpu")
    return np.split(both, np.cumsum([len(t) for t in tests])[:-1])


def cached(path: Path, compute) -> list[np.ndarray]:
    if path.exists():
        data = np.load(path)
        return [data[k] for k in data.files]
    result = compute()
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, *result)
    return result


def family_accuracy(y, pred) -> float:
    fam = pd.Series(np.asarray(y)).map(FAMILY).to_numpy() == pd.Series(np.asarray(pred)).map(
        FAMILY).to_numpy()
    return float(fam.mean())


def holdout(grid, args) -> dict:
    tok = AutoTokenizer.from_pretrained(args.model)
    rows = []
    for seed in args.seeds:
        train, test = make_split(grid, 150, 220, seed)
        classes = np.array(sorted(train[LABEL].unique()))
        y, prompts = test[LABEL].to_numpy(), test[PROMPT].to_numpy()
        base = args.cache_dir / f"holdout{seed}"
        p = {name: cached(base / f"{name}.npz", lambda n=name: [holdout_proba(n, train, test, classes)])[0]
             for name in SPARSE}
        p["frozen"] = cached(base / "frozen.npz",
                             lambda: frozen_proba(args.model, tok, train, [test], classes))[0]
        p["tuned"] = cached(base / "tuned.npz",
                            lambda: tuned_proba(args.model, tok, train, [test], classes))[0]
        p["sparse_blend"] = blend([p["tfidf_lr"], p["masked_lr"]])
        p["tuned_plus_sparse"] = blend([p["tuned"], p["tfidf_lr"], p["masked_lr"]])
        ref = classes[p["sparse_blend"].argmax(axis=1)]
        row = {"seed": seed}
        for name, q in p.items():
            pred = classes[q.argmax(axis=1)]
            row[name] = {"score": balanced_accuracy(y, pred), "family": family_accuracy(y, pred)}
            if name != "sparse_blend":
                row[name]["vs_sparse_blend"] = paired_prompt_bootstrap(y, pred, ref, prompts,
                                                                       n_boot=500)
        rows.append(row)
        print(json.dumps(row), flush=True)
    return {"settings": SETTINGS, "runs": rows}


def genre(grid, args) -> dict:
    """Train on one genre, as in `genre_exp`. Does a real encoder survive what TF-IDF didn't?"""
    tok = AutoTokenizer.from_pretrained(args.model)
    rows = []
    for seed in args.seeds:
        for src, dst in (("wp", "essay"), ("essay", "wp")):
            train, same = make_split(grid[grid["genre"] == src], 150, 220, seed)
            _, other = make_split(grid[grid["genre"] == dst], 150, 220, seed)
            classes = np.array(sorted(train[LABEL].unique()))
            tuned = cached(args.cache_dir / f"genre{seed}_{src}.npz",
                           lambda: tuned_proba(args.model, tok, train, [same, other], classes))
            rows.append({"seed": seed, "train": src, "same_genre": score(same[LABEL], tuned[0], classes),
                         "other_genre": score(other[LABEL], tuned[1], classes)})
            print(rows[-1], flush=True)
    return {"settings": SETTINGS, "runs": rows}


def cv(grid, args) -> dict:
    """Grouped 5-fold on one split: does the honest estimate still work for a transformer?"""
    tok = AutoTokenizer.from_pretrained(args.model)
    seed = args.seeds[0]
    train, _ = make_split(grid, 150, 220, seed)
    classes = np.array(sorted(train[LABEL].unique()))
    folds = grouped_folds(train, 5, 42)
    proba = np.zeros((len(train), len(classes)))
    for k in range(5):
        fit, val = train[folds != k], train[folds == k]
        proba[folds == k] = cached(args.cache_dir / f"cv{seed}_fold{k}.npz",
                                   lambda: tuned_proba(args.model, tok, fit, [val], classes))[0]
        print(k, score(val[LABEL], proba[folds == k], classes), flush=True)
    return {"seed": seed, "grouped_oof": score(train[LABEL], proba, classes)}


STAGES = {"holdout": holdout, "genre": genre, "cv": cv}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=sorted(STAGES))
    ap.add_argument("--model", required=True)
    ap.add_argument("--seeds", type=int, nargs="+", default=[100])
    ap.add_argument("--cache", type=Path, default=Path("data/proxy/cache"))
    ap.add_argument("--cache-dir", type=Path, default=Path("artifacts/transformer"))
    ap.add_argument("--out", type=Path, default=Path("reports/proxy"))
    args = ap.parse_args()
    result = STAGES[args.stage](read_grid(args.cache), args)
    path = args.out / f"transformer_{args.stage}.json"
    path.write_text(json.dumps(result, indent=1, default=float))
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
