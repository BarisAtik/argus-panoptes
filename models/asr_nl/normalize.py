"""Dutch-aware text normalization for scoring.

Naive WER punishes a model for writing "12" where the reference says "twaalf". Whatever the
normalizer does changes the headline number, so each step is explicit and the report shows the
sensitivity (see `evaluate.py`), rather than one number hiding those choices.
"""

from __future__ import annotations

import re
import unicodedata

UNITS = ["nul", "een", "twee", "drie", "vier", "vijf", "zes", "zeven", "acht", "negen", "tien",
         "elf", "twaalf", "dertien", "veertien", "vijftien", "zestien", "zeventien", "achttien",
         "negentien"]
TENS = ["", "", "twintig", "dertig", "veertig", "vijftig", "zestig", "zeventig", "tachtig",
        "negentig"]


def number_to_dutch(n: int) -> str:
    """Cardinal numbers in Dutch spelling: 21 -> eenentwintig, 22 -> tweeëntwintig."""
    if n < 0:
        return "min " + number_to_dutch(-n)
    if n < 20:
        return UNITS[n]
    if n < 100:
        tens, unit = divmod(n, 10)
        if unit == 0:
            return TENS[tens]
        word = UNITS[unit]
        joiner = "ën" if word.endswith("e") else "en"
        return f"{word}{joiner}{TENS[tens]}"
    if n < 1000:
        hundreds, rest = divmod(n, 100)
        head = "honderd" if hundreds == 1 else f"{UNITS[hundreds]}honderd"
        return head + (number_to_dutch(rest) if rest else "")
    if n < 1_000_000:
        thousands, rest = divmod(n, 1000)
        head = "duizend" if thousands == 1 else f"{number_to_dutch(thousands)}duizend"
        return head + (" " + number_to_dutch(rest) if rest else "")
    if n < 1_000_000_000:
        millions, rest = divmod(n, 1_000_000)
        return f"{number_to_dutch(millions)} miljoen" + (
            " " + number_to_dutch(rest) if rest else ""
        )
    return " ".join(UNITS[int(d)] for d in str(n))


_NUMBER = re.compile(r"(?<![\w])\d+(?:[.,]\d+)*(?![\w])")
_ELISION = {"'t": "het", "'n": "een", "'k": "ik", "m'n": "mijn", "z'n": "zijn", "d'r": "haar"}
_APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "`": "'", "´": "'"})
_DASHES = re.compile(r"[-–—_/]")
_NOT_WORD = re.compile(r"[^\w' ]+", re.UNICODE)


def strip_diacritics(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _spell_number(match: re.Match) -> str:
    token = match.group()
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", token):  # Dutch thousands: 12.500
        return number_to_dutch(int(token.replace(".", "")))
    if re.fullmatch(r"\d+", token):
        if len(token) > 1 and token.startswith("0"):
            return " ".join(UNITS[int(d)] for d in token)
        return number_to_dutch(int(token))
    whole, rest = re.split(r"[.,]", token, maxsplit=1)
    digits = " ".join(UNITS[int(d)] for d in rest if d.isdigit())
    return f"{number_to_dutch(int(whole))} komma {digits}"


def normalize_dutch(
    text: str, *, diacritics: bool = True, numbers: bool = True, elisions: bool = True
) -> str:
    """Lowercase, unify punctuation, optionally spell numbers and expand 't -> het."""
    text = unicodedata.normalize("NFC", text).translate(_APOSTROPHES).lower()
    if numbers:
        text = _NUMBER.sub(_spell_number, text)
    text = _DASHES.sub(" ", text)
    text = _NOT_WORD.sub(" ", text)
    tokens = [t.strip("'") if t not in _ELISION else t for t in text.split()]
    if elisions:
        tokens = [_ELISION.get(t, t) for t in tokens]
    text = " ".join(t for t in tokens if t)
    return strip_diacritics(text) if not diacritics else text
