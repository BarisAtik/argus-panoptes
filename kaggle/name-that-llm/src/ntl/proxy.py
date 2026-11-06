"""Build a real-text stand-in for the competition from the public Ghostbuster data.

Until the Kaggle files are here, everything else in this project has only seen fake passages. The
Ghostbuster data (CC BY 3.0, Verma et al., https://arxiv.org/abs/2305.15047) has the shape that
matters: one prompt answered by several authors. Each of 1,000 prompts in two genres has a human
text, a Claude text and five GPT variants, so it is a real prompt x author grid with siblings.

    python -m ntl.proxy download --cache data/proxy/cache
    python -m ntl.proxy build --cache data/proxy/cache --out data/proxy/comp --genres wp \
        --train-prompts 150 --test-prompts 220

`build` writes train.csv and test.csv in the competition's schema, plus test_labels.csv, so the
ordinary pipeline runs on it unchanged.

This is a proxy, not the competition. It has 7 authors rather than 18, older models, and only
two genres. Use it to learn how the validation behaves, not to forecast a leaderboard score.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

BASE = "https://raw.githubusercontent.com/vivek3141/ghostbuster-data/master"
GENRES = ("wp", "essay")
AUTHORS = ("human", "claude", "gpt", "gpt_prompt1", "gpt_prompt2", "gpt_writing", "gpt_semantic")
N_PROMPTS = 1000
MIN_WORDS, MAX_WORDS = 40, 250  # the competition's stated passage length
FAMILY = {a: ("gpt" if a.startswith("gpt") else a) for a in AUTHORS}


def download(cache: Path, workers: int = 6, tries: int = 4) -> int:
    """Fetch every text once. Files already cached are skipped, so reruns are cheap.

    A connection dropped by a proxy must not end the run halfway: a partial cache quietly builds a
    tiny, easy dataset (`build` now refuses one), so failed files are retried with a pause.
    """
    import time

    import requests

    session = requests.Session()

    def get(url: str):
        for attempt in range(tries):
            try:
                return session.get(url, timeout=30)
            except requests.RequestException:
                time.sleep(2 ** attempt)
        return None

    def fetch(rel: str) -> bool:
        path = cache / rel
        if path.exists():
            return True
        reply = get(f"{BASE}/{rel}")
        if reply is None:
            return False
        if reply.status_code != 200:
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(reply.content)
        return True

    wanted = [f"{g}/{a}/{i}.txt" for g in GENRES for a in AUTHORS
              for i in range(1, N_PROMPTS + 1)]
    with ThreadPoolExecutor(workers) as pool:
        got = sum(pool.map(fetch, wanted))
    print(f"{got}/{len(wanted)} files available in {cache}")
    return got


def read_grid(cache: Path, genres=GENRES) -> pd.DataFrame:
    """One row per cached text: genre, numeric prompt, author, raw text."""
    rows = []
    for genre in genres:
        for author in AUTHORS:
            for path in sorted((cache / genre / author).glob("*.txt")):
                text = path.read_text(encoding="utf-8", errors="replace").strip()
                rows.append((genre, int(path.stem), author, text))
    return pd.DataFrame(rows, columns=["genre", "num", "model", "text"])


def cut_passages(df: pd.DataFrame, seed: int = 0) -> pd.DataFrame:
    """Cut each text to a random length in the competition's range.

    The length is drawn independently of the author. Raw lengths differ a lot by author, so
    without this a model could learn the length rather than the writing.
    """
    rng = np.random.default_rng(seed)
    words = df["text"].str.split()
    keep = (words.str.len() >= MIN_WORDS).to_numpy()
    out = df.loc[keep].copy()
    words = words[keep]
    target = rng.integers(MIN_WORDS, MAX_WORDS + 1, len(out))
    out["text"] = [" ".join(w[:n]) for w, n in zip(words, target)]
    return out.reset_index(drop=True)


def complete_prompts(df: pd.DataFrame) -> pd.Index:
    """Prompts that every author answered, which keeps the grid exact."""
    n = df["model"].nunique()
    per = df.groupby("prompt_id")["model"].nunique()
    return per.index[per == n]


def make_split(grid: pd.DataFrame, train_prompts: int, test_prompts: int,
               seed: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Disjoint train and test prompts, with shuffled rows and ids that reveal nothing."""
    frame = cut_passages(grid, seed)
    frame["prompt_id"] = frame["genre"] + "_" + frame["num"].astype(str)
    prompts = complete_prompts(frame).to_numpy()
    rng = np.random.default_rng(seed)
    rng.shuffle(prompts)
    if train_prompts + test_prompts > len(prompts):
        raise ValueError(f"asked for {train_prompts + test_prompts}, have {len(prompts)} prompts")
    if grid["model"].nunique() < len(AUTHORS):
        raise ValueError(f"only {grid['model'].nunique()} of {len(AUTHORS)} authors: partial cache?")
    train = frame[frame["prompt_id"].isin(prompts[:train_prompts])]
    test = frame[frame["prompt_id"].isin(prompts[train_prompts:train_prompts + test_prompts])]
    return _shuffle(train, seed), _shuffle(test, seed + 1)


def _shuffle(df: pd.DataFrame, seed: int) -> pd.DataFrame:
    out = df.sample(frac=1, random_state=seed).reset_index(drop=True)
    out.insert(0, "id", np.random.default_rng(seed).permutation(len(out)))
    return out


def write_comp(train: pd.DataFrame, test: pd.DataFrame, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    train[["id", "prompt_id", "text", "model"]].to_csv(out / "train.csv", index=False)
    test[["id", "text"]].to_csv(out / "test.csv", index=False)
    test[["id", "prompt_id", "model", "genre"]].to_csv(out / "test_labels.csv", index=False)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["download", "build"])
    ap.add_argument("--cache", type=Path, default=Path("data/proxy/cache"))
    ap.add_argument("--out", type=Path, default=Path("data/proxy/comp"))
    ap.add_argument("--genres", nargs="+", default=list(GENRES))
    ap.add_argument("--train-prompts", type=int, default=150)
    ap.add_argument("--test-prompts", type=int, default=220)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    if args.command == "download":
        download(args.cache)
        return
    train, test = make_split(read_grid(args.cache, tuple(args.genres)), args.train_prompts,
                             args.test_prompts, args.seed)
    write_comp(train, test, args.out)
    print(f"train {len(train)} rows, test {len(test)} rows -> {args.out}")


if __name__ == "__main__":
    main()
