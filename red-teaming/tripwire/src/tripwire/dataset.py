"""Turn payloads and benign text into labelled documents, under different split rules.

Payloads are placed inside benign carriers, and negatives are drawn from the same
carriers. Otherwise a model can score well by learning "short odd text versus long
normal text", which is the shortcut the `bare` regime measures.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

from .sources import Benign, Payload

MAX_CHARS = 768
BARE_SHARE = 0.25


@dataclass(frozen=True)
class Doc:
    text: str
    label: int
    source: str
    group: str
    payload: str = ""


def embed(payload: str, carrier: str, rng: random.Random) -> str:
    """Insert at a sentence boundary, keeping the payload intact within MAX_CHARS."""
    room = max(0, MAX_CHARS - len(payload) - 2)
    c = carrier[:room]
    cuts = [m.end() for m in re.finditer(r"[.!?\n]\s", c)] or [len(c)]
    at = rng.choice([0, *cuts, len(c)])
    return (c[:at] + "\n" + payload + "\n" + c[at:])[:MAX_CHARS]


def build(payloads: list[Payload], carriers: list[Benign], n_pos: int, rng: random.Random, bare_share: float = BARE_SHARE,
          n_neg: int | None = None) -> list[Doc]:
    docs = []
    for _ in range(n_pos):
        p = rng.choice(payloads)
        c = rng.choice(carriers)
        text = p.text[:MAX_CHARS] if rng.random() < bare_share else embed(p.text, c.text, rng)
        docs.append(Doc(text, 1, p.source, p.group, p.text))
    pool = list(carriers)
    rng.shuffle(pool)
    n_neg = n_pos if n_neg is None else n_neg
    docs += [Doc(c.text[:MAX_CHARS], 0, c.source, "neg:" + c.source) for c in (pool * (n_neg // len(pool) + 1))[:n_neg]]
    rng.shuffle(docs)
    return docs


def split_groups(payloads: list[Payload], frac: float, rng: random.Random) -> tuple[list[Payload], list[Payload]]:
    """Whole templates go to one side."""
    groups = sorted({p.group for p in payloads})
    rng.shuffle(groups)
    held = set(groups[: max(1, int(len(groups) * frac))])
    return [p for p in payloads if p.group not in held], [p for p in payloads if p.group in held]


def split_list(items: list, frac: float, rng: random.Random) -> tuple[list, list]:
    items = list(items)
    rng.shuffle(items)
    k = max(1, int(len(items) * frac))
    return items[k:], items[:k]


def naive_leak(train: list[Doc], test: list[Doc]) -> dict[str, float]:
    """How much of a test set is already in the training set."""
    seen_payloads = {d.payload for d in train if d.label}
    seen_docs = {d.text for d in train}
    pos = [d for d in test if d.label]
    return {"payload_seen": sum(d.payload in seen_payloads for d in pos) / max(1, len(pos)),
            "doc_seen": sum(d.text in seen_docs for d in test) / max(1, len(test))}
