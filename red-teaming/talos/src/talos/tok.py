"""Closed word vocabulary plus entity slots.

Any word outside the vocabulary becomes an entity slot, numbered by first use after a random shuffle. So the model
learns to copy slots rather than names, and every test name can be new.
"""

from __future__ import annotations

import random

from .world import ASSETS, FIELDS, ITEMS, TOPICS

SPECIAL = ["<pad>", "<eos>"]
GRAMMAR = """user assistant document : . begin data end call send_email to body pay amount read_doc id reply
the what is do says follow has your instructions carry out note open send email forward mail in and a of on at for
ignore task forget earlier steps stop now instead please could you it would help if kindly when can new from admin all
staff must policy update are required security team read this then see before answer next step plan what happens
agent last week said went was sent by meeting moved monday lunch with noon joined shared thanks review weather fine
talked about office closed friday printer second floor fixed well""".split()
WORDS = list(dict.fromkeys(SPECIAL + GRAMMAR + ITEMS + ASSETS + FIELDS + TOPICS))
N_SLOTS = 40
STOI = {w: i for i, w in enumerate(WORDS)}
SLOT0 = len(WORDS)
VOCAB = SLOT0 + N_SLOTS
PAD, EOS = STOI["<pad>"], STOI["<eos>"]


class Slots:
    """One sample's map between entity strings and slot ids."""

    def __init__(self, rng: random.Random | None = None):
        self.order = list(range(N_SLOTS))
        if rng:
            rng.shuffle(self.order)
        self.fwd: dict[str, int] = {}
        self.back: dict[int, str] = {}

    def encode(self, w: str) -> int:
        if w in STOI:
            return STOI[w]
        if w not in self.fwd:
            if len(self.fwd) >= N_SLOTS:  # out of slots: reuse the last one, a known toy limit
                return SLOT0 + self.order[-1]
            i = SLOT0 + self.order[len(self.fwd)]
            self.fwd[w], self.back[i] = i, w
        return self.fwd[w]

    def decode(self, i: int) -> str:
        if i < SLOT0:
            return WORDS[i]
        return self.back.get(i, "<unk>")
