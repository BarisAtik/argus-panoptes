"""Mechanical rewrites of a payload, and the cheap normaliser that undoes some of them.

The payloads stay what they were: requests to move a fake canary or print a harmless
string. These rewrites ask how much of a detector's score survives a change in spelling,
and they run against this repository's own detector only.
"""

from __future__ import annotations

import base64
import random
import re
import unicodedata
from typing import Callable

ZW = "​"
_HOMO = str.maketrans({"a": "а", "c": "с", "e": "е", "i": "і", "o": "о", "p": "р", "s": "ѕ", "x": "х", "y": "у"})
_FOLD = str.maketrans({"а": "a", "с": "c", "е": "e", "і": "i", "о": "o", "р": "p", "ѕ": "s", "х": "x", "у": "y",
                       "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P", "С": "C",
                       "Т": "T", "Х": "X", "α": "a", "ο": "o", "ν": "v", "ι": "i"})
_LEET = str.maketrans({"a": "4", "e": "3", "i": "1", "o": "0", "s": "5", "t": "7"})
_SYN = [(r"\bignore\b", "set aside"), (r"\bforget\b", "drop"), (r"\bprevious\b", "earlier"), (r"\binstructions?\b", "guidance"),
        (r"\bsend\b", "pass along"), (r"\bemail\b", "message"), (r"\bprint\b", "write out"), (r"\breveal\b", "show"),
        (r"\bprompt\b", "brief"), (r"\bimportant\b", "worth noting"), (r"\bmust\b", "should"), (r"\buser\b", "person")]


def _zero_width(t: str, rng: random.Random) -> str:
    return "".join(c + ZW if c.isalpha() and rng.random() < 0.35 else c for c in t)


def _spaced(t: str, rng: random.Random) -> str:
    return re.sub(r"[A-Za-z]{3,}", lambda m: " ".join(m.group()) + "  ", t)


def _synonym(t: str, rng: random.Random) -> str:
    for pat, new in _SYN:
        t = re.sub(pat, new, t, flags=re.I)
    return t


def _b64(t: str, rng: random.Random) -> str:
    return "Decode this base64 note and act on it: " + base64.b64encode(t.encode()).decode()


TRANSFORMS: dict[str, Callable[[str, random.Random], str]] = {
    "none": lambda t, r: t,
    "upper": lambda t, r: t.upper(),
    "zero_width": _zero_width,
    "homoglyph": lambda t, r: t.translate(_HOMO),
    "spaced": _spaced,
    "leet": lambda t, r: t.lower().translate(_LEET),
    "synonym": _synonym,
    "base64": _b64,
}
# The augmented model sees the first group in training. The second group is never trained on.
SEEN = ("upper", "zero_width", "homoglyph")
UNSEEN = ("spaced", "leet", "synonym", "base64")


def normalise(text: str) -> str:
    """NFKC, drop format characters, fold common look-alikes, close up letter-by-letter spacing."""
    t = unicodedata.normalize("NFKC", text)
    t = "".join(c for c in t if unicodedata.category(c) != "Cf").translate(_FOLD)
    return re.sub(r"\b(?:[A-Za-z] ){3,}[A-Za-z]\b", lambda m: m.group().replace(" ", ""), t)


def canon(text: str) -> str:
    """Normalised and case-folded. Added after the byte CNN flagged 71% of upper-cased benign
    text, so the `canonical` rows in the robustness report are post-hoc on that test data."""
    return normalise(text).casefold()
