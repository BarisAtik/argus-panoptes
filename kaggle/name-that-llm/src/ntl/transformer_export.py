"""Flatten cached holdout predictions into one long file for R/05_transformer_audit.R.

    python -m ntl.transformer_export --seeds 100 101 --out artifacts/transformer/predictions.parquet
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from .cv import blend
from .data import LABEL, PROMPT
from .proxy import make_split, read_grid

CANDIDATES = ("tfidf_lr", "masked_lr", "frozen", "tuned")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, nargs="+", default=[100, 101])
    ap.add_argument("--cache", type=Path, default=Path("data/proxy/cache"))
    ap.add_argument("--cache-dir", type=Path, default=Path("artifacts/transformer"))
    ap.add_argument("--out", type=Path, default=Path("artifacts/transformer/predictions.parquet"))
    args = ap.parse_args()
    grid = read_grid(args.cache)
    rows = []
    for seed in args.seeds:
        train, test = make_split(grid, 150, 220, seed)
        classes = np.array(sorted(train[LABEL].unique()))
        p = {n: np.load(args.cache_dir / f"holdout{seed}" / f"{n}.npz")["arr_0"] for n in CANDIDATES}
        p["sparse_blend"] = blend([p["tfidf_lr"], p["masked_lr"]])
        p["tuned_plus_sparse"] = blend([p["tuned"], p["tfidf_lr"], p["masked_lr"]])
        frame = pd.DataFrame({"seed": seed, "prompt_id": test[PROMPT].to_numpy(),
                              "model": test[LABEL].to_numpy()})
        for name, q in p.items():
            frame[f"pred_{name}"] = classes[q.argmax(axis=1)]
        rows.append(frame)
    pd.concat(rows).to_parquet(args.out, index=False)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
