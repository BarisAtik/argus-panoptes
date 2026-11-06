"""Score redactors on the benchmark. Output goes to runs/pii_nl, nothing there is committed.

    python -m pii_nl.run score --split dev --systems patterns spacy_lg deduce
    python -m pii_nl.run report --split test
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from forge.report import markdown_table, run_metadata, write_report
from ner_nl.names import NAMES

from .evaluate import evaluate, rate
from .generate import generate

OUT = Path("runs/pii_nl")
SPACY = {f"spacy_{s}": f"nl_core_news_{s}" for s in ("sm", "md", "lg")}
REGISTERS = ("brief", "mail", "chat", "transcript", "beschikking", "notitie")
KINDS = (
    "PERSOON", "ADRES", "POSTCODE", "TELEFOON", "E-MAIL", "IBAN", "BSN", "GEBOORTEDATUM",
    "KENTEKEN",
)


def _spans(hits) -> list[tuple[int, int]]:
    return [(h.start, h.end) for h in hits]


def build(name: str):
    """Return text -> masked character ranges for a system name."""
    from ner_nl.redact import model_hits, pattern_hits

    if name == "patterns":
        return lambda text: _spans(pattern_hits(text))
    if name in SPACY:
        import spacy

        nlp = spacy.load(SPACY[name])
        return lambda text: _spans(pattern_hits(text) + model_hits(text, nlp))
    if name == "deduce":
        import deduce

        engine = deduce.Deduce()
        return lambda text: [
            (a.start_char, a.end_char) for a in engine.deidentify(text).annotations
        ]
    if name in ("rules", "rules_lg"):
        from .rules import rule_hits

        if name == "rules":
            return lambda text: _spans(rule_hits(text))
        import spacy

        nlp = spacy.load(SPACY["spacy_lg"])
        return lambda text: _spans(rule_hits(text, nlp))
    raise ValueError(f"unknown system {name}")


def stage_score(args) -> None:
    docs = generate(args.split, repeats=args.repeats, seed=args.seed)
    OUT.mkdir(parents=True, exist_ok=True)
    for name in args.systems:
        rows = evaluate(docs, build(name))
        path = OUT / f"{args.split}_{name}.csv"
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        print(name, json.dumps(rate(rows, kind=None)), flush=True)


def load_rows(split: str, name: str) -> list[dict]:
    with open(OUT / f"{split}_{name}.csv", encoding="utf-8") as handle:
        return [
            {**r, "leaked": int(r["leaked"]), "total": int(r["total"]), "repeat": int(r["repeat"])}
            for r in csv.DictReader(handle)
        ]


def fmt(row: dict) -> str:
    if row["n"] == 0:
        return "-"
    if row.get("low") is None:
        return f"{row['rate']:.3f}"
    return f"{row['rate']:.3f} ({max(row['low'], 0):.3f} to {min(row['high'], 1):.3f})"


def stage_report(args) -> None:
    systems = sorted(
        p.stem.removeprefix(f"{args.split}_") for p in OUT.glob(f"{args.split}_*.csv")
    )
    data = {name: load_rows(args.split, name) for name in systems}
    overall, by_kind, by_register, by_group = [], [], [], []
    for name, rows in data.items():
        overall.append(
            {
                "system": name,
                "all personal data": fmt(rate(rows, kind=None)),
                "persons": fmt(rate(rows, kind="PERSOON")),
                "ordinary words masked": fmt(rate(rows, kind="_outside")),
                "distractors masked": fmt(rate(rows, kind="_distractor")),
            }
        )
        by_kind.append({"system": name, **{k: fmt(rate(rows, kind=k)) for k in KINDS}})
        by_register.append(
            {"system": name, **{r: fmt(rate(rows, kind="PERSOON", register=r)) for r in REGISTERS}}
        )
        by_group.append(
            {"system": name, **{g: fmt(rate(rows, kind="PERSOON", group=g)) for g in NAMES}}
        )
    report = {
        "meta": run_metadata("real", ("spacy", "deduce", "nl_core_news_lg"), split=args.split),
        "overall": overall,
        "by_kind": by_kind,
        "person_by_register": by_register,
        "person_by_tradition": by_group,
    }
    md = [
        f"# Dutch redaction benchmark: {args.split}\n",
        "Synthetic documents only. Share of values with any word left readable, 95% cluster t "
        f"intervals over templates. Commit {report['meta']['git_sha']}, "
        f"{report['meta']['created_utc']}.\n",
        "## Overall\n", markdown_table(overall),
        "## Leak by kind\n", markdown_table(by_kind),
        "## Person leak by register\n", markdown_table(by_register),
        "## Person leak by naming tradition\n", markdown_table(by_group),
    ]
    write_report(OUT / f"report_{args.split}", report, "\n".join(md))
    print("\n".join(md))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["score", "report"])
    parser.add_argument("--split", default="dev", choices=["dev", "test"])
    parser.add_argument("--systems", nargs="+", default=["patterns"])
    parser.add_argument("--repeats", type=int, default=8)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    {"score": stage_score, "report": stage_report}[args.stage](args)


if __name__ == "__main__":
    main()
