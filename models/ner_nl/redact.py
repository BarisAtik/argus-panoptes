"""Redact Dutch text with checked patterns plus a spaCy pipeline. Runs locally, sends nothing out.

    python -m ner_nl.redact notes.txt --model nl_core_news_lg
    echo "Bel Sanne Bakker op 06-12345678" | python -m ner_nl.redact -

Pattern matches are validated where the format allows it (IBAN mod 97, the BSN eleven test), so
digits that merely look right stay in. The name part is only as good as the model: see the
measured miss rates in results/ner_nl/. Treat the output as a first pass that a person reviews.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass

MODEL_LABELS = {
    "PERSON": "PERSOON",
    "GPE": "LOCATIE",
    "LOC": "LOCATIE",
    "FAC": "LOCATIE",
    "ORG": "ORGANISATIE",
}


@dataclass(frozen=True)
class Hit:
    start: int
    end: int
    kind: str
    source: str


def iban_valid(text: str) -> bool:
    compact = re.sub(r"\s", "", text).upper()
    moved = compact[4:] + compact[:4]
    digits = "".join(str(int(c, 36)) for c in moved)
    return int(digits) % 97 == 1


def bsn_valid(text: str) -> bool:
    digits = [int(c) for c in re.sub(r"\D", "", text)]
    if len(digits) != 9:
        return False
    weights = (9, 8, 7, 6, 5, 4, 3, 2, -1)
    return sum(d * w for d, w in zip(digits, weights)) % 11 == 0 and sum(digits) > 0


def _national_digits(text: str) -> str:
    """The nine digits after the trunk 0 or country code, which every Dutch number has."""
    digits = re.sub(r"\D", "", text.replace("(0)", ""))
    for prefix in ("0031", "31", "0"):
        if digits.startswith(prefix):
            return digits[len(prefix) :]
    return digits


PATTERNS: tuple[tuple[str, re.Pattern, Callable[[str], bool] | None], ...] = (
    ("E-MAIL", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b"), None),
    ("URL", re.compile(r"\b(?:https?://|www\.)\S*[\w/]", re.I), None),
    (
        "IBAN",
        re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){2,6}(?:\s?[A-Z0-9]{1,3})?\b"),
        iban_valid,
    ),
    ("BSN", re.compile(r"(?<![\d-])\d{4}[.\s]?\d{2}[.\s]?\d{3}(?![\d-])"), bsn_valid),
    ("BSN", re.compile(r"(?<![\d-])\d{3}[.\s]\d{3}[.\s]\d{3}(?![\d-])"), bsn_valid),
    (
        "TELEFOON",
        re.compile(
            r"(?<![\d+])(?:\+31[\s-]?(?:\(0\)[\s-]?)?|0031[\s-]?|0)"
            r"[1-9](?:[\s-]?\d){8}(?!\d)"
        ),
        lambda t: len(_national_digits(t)) == 9,
    ),
    ("POSTCODE", re.compile(r"\b[1-9]\d{3}\s?(?!SA|SD|SS)[A-Z]{2}\b"), None),
    ("IP", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), None),
)


def pattern_hits(text: str) -> list[Hit]:
    hits = []
    for kind, pattern, check in PATTERNS:
        for match in pattern.finditer(text):
            if check is None or check(match.group()):
                hits.append(Hit(match.start(), match.end(), kind, "pattern"))
    return hits


def model_hits(text: str, nlp) -> list[Hit]:
    return [
        Hit(e.start_char, e.end_char, MODEL_LABELS[e.label_], "model")
        for e in nlp(text).ents
        if e.label_ in MODEL_LABELS
    ]


def merge(hits: Iterable[Hit]) -> list[Hit]:
    """Keep one hit per stretch of text. Patterns beat the model, longer beats shorter."""
    ranked = sorted(hits, key=lambda h: (h.source != "pattern", h.start - h.end, h.start))
    kept: list[Hit] = []
    for hit in ranked:
        if all(hit.end <= k.start or k.end <= hit.start for k in kept):
            kept.append(hit)
    return sorted(kept, key=lambda h: h.start)


def redact(text: str, nlp=None) -> tuple[str, list[Hit]]:
    hits = pattern_hits(text)
    if nlp is not None:
        hits += model_hits(text, nlp)
    kept = merge(hits)
    parts, cursor = [], 0
    for hit in kept:
        parts += [text[cursor : hit.start], f"[{hit.kind}]"]
        cursor = hit.end
    parts.append(text[cursor:])
    return "".join(parts), kept


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="text file, or - for standard input")
    parser.add_argument("--model", default="nl_core_news_lg", help="spaCy model, or none")
    args = parser.parse_args()
    text = sys.stdin.read() if args.path == "-" else open(args.path, encoding="utf-8").read()
    nlp = None
    if args.model != "none":
        import spacy

        nlp = spacy.load(args.model)
    print(redact(text, nlp)[0])


if __name__ == "__main__":
    main()
