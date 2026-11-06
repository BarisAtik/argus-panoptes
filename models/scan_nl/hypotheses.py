"""Check the registered hypotheses on stored rows from `scan_nl.run score`. Prints JSON."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy import stats

from forge.stats import ratio_ci_t

from .run import OUT, load

GOLD = "PERSOON ADRES POSTCODE TELEFOON E-MAIL IBAN BSN GEBOORTEDATUM KENTEKEN".split()
HARD = ("dpi_100", "fax", "photocopy", "phone")
MILD = ("dpi_200", "dpi_150", "jpeg", "noise", "blur", "skew_1")


def pick(rows, engine, conditions=None, defence="none", kinds=GOLD, group=None) -> list[dict]:
    return [
        r for r in rows
        if r["engine"] == engine and r["defence"] == defence and r["kind"] in kinds
        and (conditions is None or r["condition"] in conditions)
        and (group is None or r["group"] == group)
    ]


def ratio(rows: list[dict]) -> dict:
    if not rows:
        return {"rate": float("nan"), "low": float("nan"), "high": float("nan")}
    leaked = np.array([r["leaked"] for r in rows], dtype=float)
    total = np.array([r["total"] for r in rows], dtype=float)
    ci = ratio_ci_t(leaked, total, [r["template"] for r in rows])
    return {"rate": float(leaked.sum() / total.sum()), "low": float(ci.low), "high": float(ci.high)}


def paired(one: list[dict], two: list[dict]) -> dict:
    """Rate of `one` minus rate of `two`, cluster t over templates, same templates in both."""
    sums = {}
    for name, rows in (("a", one), ("b", two)):
        cell: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
        for r in rows:
            cell[r["template"]][0] += r["leaked"]
            cell[r["template"]][1] += r["total"]
        sums[name] = cell
    templates = sorted(sums["a"])
    if not templates:
        return {"gap": float("nan"), "low": float("nan"), "high": float("nan")}
    a = np.array([sums["a"][t] for t in templates])
    b = np.array([sums["b"][t] for t in templates])
    ra, rb = a[:, 0].sum() / a[:, 1].sum(), b[:, 0].sum() / b[:, 1].sum()
    # Linearised ratio difference per template.
    score = (a[:, 0] - ra * a[:, 1]) / a[:, 1].mean() - (b[:, 0] - rb * b[:, 1]) / b[:, 1].mean()
    k = len(templates)
    half = stats.t.ppf(0.975, k - 1) * score.std(ddof=1) / np.sqrt(k)
    return {"gap": float(ra - rb), "low": float(ra - rb - half), "high": float(ra - rb + half)}


def pages(rows: list[dict]) -> list[dict]:
    """Leaked and total values per page, with its signals."""
    table: dict[tuple, dict] = {}
    for r in rows:
        key = (r["template"], r["group"], r["repeat"], r["condition"])
        row = table.setdefault(key, {"leaked": 0, "total": 0, "conf": r["conf"],
                                     "unread": float(r["unread"])})
        row["leaked"] += r["leaked"]
        row["total"] += r["total"]
    return list(table.values())


def alarm(rows: list[dict], threshold: float = 0.05) -> dict:
    book = pages(rows)
    flagged = sorted(book, key=lambda p: -p["unread"])
    count = sum(p["unread"] > threshold for p in book)
    by_conf = sorted(book, key=lambda p: p["conf"])[:count]
    leaked = sum(p["leaked"] for p in book)
    caught = sum(p["leaked"] for p in flagged[:count])
    caught_conf = sum(p["leaked"] for p in by_conf)
    kept = flagged[count:]
    return {
        "pages": len(book), "flagged": count, "leaked_values": leaked,
        "caught_by_rule": caught, "caught_by_confidence": caught_conf,
        "leak_on_unflagged_pages": sum(p["leaked"] for p in kept)
        / max(sum(p["total"] for p in kept), 1),
    }


def check(split: str = "blind") -> dict:
    rows = load(split)
    text = load(split, "text")
    for r in (*rows, *text):
        r["cer"] = float(r["cer"])
    out = {}
    out["h1"] = {"truth": ratio(pick(rows, "truth")), "pass_if": "rate <= 0.08"}
    for condition in ("photocopy", "phone"):
        out[f"h2_{condition}"] = {
            "pixel": ratio(pick(rows, "tesseract_nld", (condition,))),
            "text": ratio(pick(text, "tesseract_nld", (condition,))),
        }
    base = pick(rows, "tesseract_enh", ("clean_300",))
    out["h3"] = {c: paired(pick(rows, "tesseract_enh", (c,)), base) for c in MILD}
    nld, enh = pick(rows, "tesseract_nld", HARD), pick(rows, "tesseract_enh", HARD)
    out["h4"] = {"nld": ratio(nld), "enh": ratio(enh), "cut": 1 - ratio(enh)["rate"]
                 / ratio(nld)["rate"], "gap": paired(enh, nld)}
    eng = pick(rows, "tesseract_eng", ("clean_300",))
    dutch = pick(rows, "tesseract_nld", ("clean_300",))
    cer = {e: float(np.mean(list({(r["template"], r["group"]): r["cer"] for r in rows
                                  if r["engine"] == e and r["condition"] == "clean_300"}.values())))
           for e in ("tesseract_eng", "tesseract_nld")}
    out["h5"] = {"cer": cer, "leak_gap": paired(eng, dutch)}
    rapid, tess = pick(rows, "rapidocr"), pick(rows, "tesseract_enh")
    outside = ("_outside",)
    out["h6"] = {
        "leak_gap": paired(rapid, tess),
        "ordinary": {"rapidocr": ratio(pick(rows, "rapidocr", kinds=outside)),
                     "tesseract_enh": ratio(pick(rows, "tesseract_enh", kinds=outside))},
    }
    plain, closed = pick(rows, "tesseract_nld"), pick(rows, "tesseract_nld", defence="unread")
    out["h7"] = {
        "none": ratio(plain), "unread": ratio(closed),
        "cut": 1 - ratio(closed)["rate"] / ratio(plain)["rate"],
        "ordinary": ratio(pick(rows, "tesseract_nld", defence="unread", kinds=outside)),
    }
    out["h8"] = alarm(plain)
    out["h9"] = {
        "repair": paired(pick(rows, "tesseract_enh", defence="repair"), tess),
        "digits": paired(pick(rows, "tesseract_enh", defence="digits"), tess),
        "distractors": paired(
            pick(rows, "tesseract_enh", defence="digits", kinds=("_distractor",)),
            pick(rows, "tesseract_enh", kinds=("_distractor",)),
        ),
    }
    def added(group):
        return paired(
            pick(rows, "tesseract_nld", HARD, kinds=("PERSOON",), group=group),
            pick(rows, "truth", HARD, kinds=("PERSOON",), group=group),
        )

    base_added = added("dutch")
    out["h10"] = {"dutch": base_added}
    for group in ("turkish", "polish", "hindustani", "moroccan"):
        out["h10"][group] = {
            "added": added(group),
            "versus_dutch": added(group)["gap"] - base_added["gap"],
        }
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", default="blind")
    args = parser.parse_args()
    result = check(args.split)
    path = Path(OUT) / f"hypotheses_{args.split}.json"
    path.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
