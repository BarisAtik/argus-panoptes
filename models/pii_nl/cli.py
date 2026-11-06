"""Redact Dutch text on this machine. Nothing leaves it.

    python -m pii_nl.cli notes.txt                       # redacted text
    python -m pii_nl.cli notes.txt --json                # text plus every hit, for a reviewer
    echo "bel sanne bakker op 06-12345678" | python -m pii_nl.cli -
    python -m pii_nl.cli notes.txt --model none          # rules only, no spaCy needed

Treat the result as a first pass that a person checks: see the leak rates in EVALUATION_CARD.md.
"""

from __future__ import annotations

import argparse
import json
import sys

from .rules import redact


def load_model(name: str):
    if name == "none":
        return None
    import spacy

    return spacy.load(name, disable=["parser", "lemmatizer", "morphologizer", "attribute_ruler"])


def redact_json(text: str, nlp=None) -> dict:
    """Redacted text plus the hits, so a reviewer can see what was masked and why."""
    out, hits = redact(text, nlp)
    return {
        "text": out,
        "hits": [
            {
                "start": h.start,
                "end": h.end,
                "kind": h.kind,
                "source": h.source,
                "value": text[h.start : h.end],
            }
            for h in hits
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="text file, or - for standard input")
    parser.add_argument("--model", default="nl_core_news_lg", help="spaCy model, or none")
    parser.add_argument("--json", action="store_true", help="also list hits. Contains the values!")
    args = parser.parse_args()
    if args.path == "-":
        text = sys.stdin.read()
    else:
        with open(args.path, encoding="utf-8") as handle:
            text = handle.read()
    nlp = load_model(args.model)
    if args.json:
        print(json.dumps(redact_json(text, nlp), ensure_ascii=False, indent=2))
    else:
        print(redact(text, nlp)[0])


if __name__ == "__main__":
    main()
