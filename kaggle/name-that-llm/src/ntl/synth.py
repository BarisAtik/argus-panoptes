"""Fake data with the competition's schema, so everything runs without Kaggle access.

Not a proxy for real difficulty: scores on this data say the code works, nothing about the
leaderboard. It reproduces the structure that matters for validation: a prompt x model grid,
topic words that follow the prompt, and siblings inside a lab that write almost alike.

    python -m ntl.synth --out data/synth
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from .data import ID, LABEL, PROMPT, TEXT

LABS = ["alpha", "bravo", "cedar", "delta", "ember", "fjord"]
FUNCTION_WORDS = (
    "the of and to in that it is for with as on this be by are from at or an but not which we "
    "can have more these will also however while their such often may might each both between "
    "into through because although therefore moreover indeed perhaps rather quite very"
).split()
OPENERS = ("Certainly", "Overall", "In short", "Consider this", "Here is the thing", "At its core",
           "To begin", "Broadly speaking", "Interestingly", "Put simply")
SYLLABLES = "ba ce di fo gu ka le mi no pu ra se ti vo wu xa ye zi lo tan mer sol ven rik dor".split()


def _word(rng: np.random.Generator) -> str:
    return "".join(rng.choice(SYLLABLES, size=rng.integers(2, 4)))


def model_names(n_models: int = 18, n_labs: int = 6) -> dict[str, str]:
    """model name -> lab."""
    return {f"{LABS[i % n_labs]}-{i // n_labs + 1}": LABS[i % n_labs] for i in range(n_models)}


def _style(rng: np.random.Generator, n_models: int, n_labs: int, sibling_gap: float) -> list[dict]:
    """Lab-level style plus a small per-model offset. `sibling_gap` sets how separable siblings are."""
    labs = [rng.normal(0, 1, len(FUNCTION_WORDS) + len(OPENERS) + 5) for _ in range(n_labs)]
    styles = []
    for i in range(n_models):
        v = labs[i % n_labs] + rng.normal(0, sibling_gap, labs[0].shape)
        fw, op, rest = np.split(v, [len(FUNCTION_WORDS), len(FUNCTION_WORDS) + len(OPENERS)])
        styles.append({
            "fw": np.exp(fw * 0.6) / np.exp(fw * 0.6).sum(),
            "op": np.exp(op) / np.exp(op).sum(),
            "sent_len": 13 + 3 * rest[0],
            "fw_rate": np.clip(0.5 + 0.08 * rest[1], 0.2, 0.8),
            "dash": 0.04 * np.exp(rest[2]),
            "semi": 0.03 * np.exp(rest[3]),
            "list": 0.05 * np.exp(rest[4]),
        })
    return styles


def _passage(rng: np.random.Generator, style: dict, topic: np.ndarray) -> str:
    n_words = int(rng.integers(40, 251))
    sentences: list[str] = []
    made = 0
    if rng.random() < 0.5:
        sentences.append(str(rng.choice(OPENERS, p=style["op"])) + ",")
    while made < n_words:
        length = max(4, int(rng.normal(style["sent_len"], 4)))
        is_fw = rng.random(length) < style["fw_rate"]
        words = [
            str(rng.choice(FUNCTION_WORDS, p=style["fw"])) if f else str(rng.choice(topic))
            for f in is_fw
        ]
        made += length
        end = "." if rng.random() > style["semi"] else ";"
        sentence = " ".join(words)
        if rng.random() < style["dash"]:
            cut = length // 2
            sentence = " ".join(words[:cut]) + " — " + " ".join(words[cut:])
        lead = "- " if rng.random() < style["list"] else ""
        sentences.append(lead + sentence.capitalize() + end)
    return " ".join(sentences)


def make(n_prompts: int = 150, n_models: int = 18, n_labs: int = 6, n_test_prompts: int = 60,
         sibling_gap: float = 0.35, drop_rows: int = 1, seed: int = 7,
         shuffle_test: bool = True) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (train, test, test_labels). Test prompts never appear in train."""
    rng = np.random.default_rng(seed)
    names = list(model_names(n_models, n_labs))
    styles = _style(rng, n_models, n_labs, sibling_gap)

    def block(n: int, start: int) -> pd.DataFrame:
        rows = []
        for p in range(n):
            topic = np.array([_word(rng) for _ in range(25)])
            for name, style in zip(names, styles):
                rows.append({PROMPT: f"p{start + p:04d}", LABEL: name,
                             TEXT: _passage(rng, style, topic)})
        return pd.DataFrame(rows)

    train = block(n_prompts, 0).sample(frac=1, random_state=seed).reset_index(drop=True)
    if drop_rows:
        train = train.iloc[:-drop_rows].reset_index(drop=True)
    train.insert(0, ID, [f"tr{i:05d}" for i in range(len(train))])
    held = block(n_test_prompts, n_prompts)
    if shuffle_test:
        held = held.sample(frac=1, random_state=seed + 1).reset_index(drop=True)
    held.insert(0, ID, [f"te{i:05d}" for i in range(len(held))])
    return train[[ID, PROMPT, TEXT, LABEL]], held[[ID, TEXT]], held[[ID, PROMPT, LABEL]]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="data/synth")
    ap.add_argument("--prompts", type=int, default=150)
    ap.add_argument("--test-prompts", type=int, default=60)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    train, test, truth = make(args.prompts, n_test_prompts=args.test_prompts, seed=args.seed)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    train.to_csv(out / "train.csv", index=False)
    test.to_csv(out / "test.csv", index=False)
    truth.to_csv(out / "test_truth.csv", index=False)
    print(f"wrote {len(train)} train / {len(test)} test rows to {out}")


if __name__ == "__main__":
    main()
