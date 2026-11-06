"""The fixed test sets and the factorial."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import multiprocessing as mp
import os
import random
import sys
import time

import torch

from . import world as W
from .train import Config, fit, n_params, outcome, predict, save

TEST_POOL = "z"  # entity names never used in training
N = 150


def test_set(n: int = N, seed: int = 12345) -> list[tuple[str, W.Example]]:
    """(cell, example). Fixed, so that all models answer the same items."""
    rng = random.Random(seed)
    rows: list[tuple[str, W.Example]] = []
    for kind in ["send", "pay", "open", "ask"]:
        rows += [(f"direct/{kind}", W.direct(rng, TEST_POOL, kind)) for _ in range(n)]
    for fam in W.FAMILIES:
        rows += [(f"inject/{fam}", W.injected(rng, fam, TEST_POOL)) for _ in range(n)]
        rows += [(f"delegate/{fam}", W.delegate(rng, TEST_POOL, fam)) for _ in range(n)]
    rows += [("mention/all", W.mention(rng, TEST_POOL)) for _ in range(2 * n)]
    for hop in range(5):
        for fam in ["ignore", "polite", "authority", "story"]:
            rows += [(f"hop{hop}/inject/{fam}", W.injected(rng, fam, TEST_POOL, hop)) for _ in range(n // 3)]
            rows += [(f"hop{hop}/delegate/{fam}", W.delegate(rng, TEST_POOL, fam, hop)) for _ in range(n // 3)]
    return rows


def model_grid(seeds: int = 4) -> list[Config]:
    grid = []
    for prov in W.PROVENANCE:
        for regime in ["clean", "delegate"]:
            grid += [Config(regime=regime, prov=prov, seed=s) for s in range(seeds)]
        grid += [Config(regime="adv", prov=prov, heldout=f, seed=i) for i, f in enumerate(W.FAMILIES)]
    return grid


def tag(c: Config) -> str:
    return f"{c.regime}-{c.prov}-{c.heldout or 'none'}-s{c.seed}"


def run_one(args) -> str:
    c, out = args
    torch.set_num_threads(1)
    name = tag(c)
    path = f"{out}/{name}.csv.gz"
    if os.path.exists(path):
        return name
    t0 = time.time()
    m = fit(c)
    rows = test_set()
    texts = predict(m, [e for _, e in rows], c.prov)
    tmp = path + ".tmp"
    with gzip.open(tmp, "wt", newline="") as f:
        w = csv.writer(f)
        w.writerow(["model", "regime", "prov", "heldout", "seed", "cell", "item", "task", "attack", "malformed"])
        for i, ((cell, ex), text) in enumerate(zip(rows, texts)):
            o = outcome(ex, text)
            w.writerow([name, c.regime, c.prov, c.heldout or "", c.seed, cell, i, o["task"], o["attack"], o["malformed"]])
    os.replace(tmp, path)
    save(m, c, f"{out}/{name}.pt")
    print(f"{name} done in {time.time() - t0:.0f}s, {n_params(m)} params", flush=True)
    return name


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="data/runs")
    p.add_argument("--jobs", type=int, default=2)
    p.add_argument("--steps", type=int, default=None)
    a = p.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    grid = model_grid()
    if a.steps:
        for c in grid:
            c.steps = a.steps
    with mp.Pool(a.jobs) as pool:
        for name in pool.imap_unordered(run_one, [(c, a.out) for c in grid]):
            print(name, file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
