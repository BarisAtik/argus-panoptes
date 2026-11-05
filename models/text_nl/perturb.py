"""Small meaning-preserving edits. A label flip here is a robustness failure by definition."""

from __future__ import annotations

import re

import numpy as np


def typos(text: str, rate: float = 0.05, seed: int = 0) -> str:
    """Swap two neighbouring letters in about `rate` of words: the most common real typo."""
    rng = np.random.default_rng(seed)
    words = text.split(" ")
    for index, word in enumerate(words):
        if len(word) > 3 and word.isalpha() and rng.random() < rate:
            pos = int(rng.integers(1, len(word) - 2)) if len(word) > 4 else 1
            words[index] = word[:pos] + word[pos + 1] + word[pos] + word[pos + 2 :]
    return " ".join(words)


def lowercase(text: str) -> str:
    return text.lower()


def strip_punctuation(text: str) -> str:
    return re.sub(r"[^\w\s]", "", text)


def add_filler(text: str) -> str:
    return "Ik heb dit boek gisteren uitgelezen. " + text


PERTURBATIONS = {
    "typos_5pct": typos,
    "lowercase": lowercase,
    "no_punctuation": strip_punctuation,
    "neutral_opening_sentence": add_filler,
}
