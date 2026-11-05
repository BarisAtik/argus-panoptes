#!/usr/bin/env python3
"""Precision and recall on labelled tools, plus false positives on third-party manifests.

Unit of analysis is the tool. A tool counts as flagged at medium or above.
The scanner is scored alone: each tool is scanned without the others, except that
real manifests are scanned as whole servers, which is how they would be used.
"""

import json
import sys
from collections import Counter
from pathlib import Path

from mcp_lens.core import Metrics, is_flagged, load_manifest, scan

root = Path(__file__).resolve().parent.parent


def score(path: Path, show: bool) -> Metrics:
    m = Metrics()
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        tools = load_manifest({"server": "x", "tools": [row]})
        hit = is_flagged(scan(tools))
        if row["label"] and hit:
            m.tp += 1
        elif row["label"]:
            m.fn += 1
        elif hit:
            m.fp += 1
        else:
            m.tn += 1
        if show and bool(row["label"]) != hit:
            print(f"  {'FN' if row['label'] else 'FP'} {row['technique']:18} {row['name']}: {row['description'][:90]}")
    return m


def main() -> None:
    show = "--show" in sys.argv
    res = {}
    for name in ("dev", "dev2", "holdout"):
        p = root / "corpus" / f"{name}.jsonl"
        if p.exists():
            m = score(p, show)
            res[name] = {"tp": m.tp, "fp": m.fp, "fn": m.fn, "tn": m.tn,
                         "precision": round(m.precision, 3), "recall": round(m.recall, 3)}
    flagged = total = 0
    rules: Counter = Counter()
    for p in sorted((root / "corpus" / "real").glob("*.json")):
        tools = load_manifest(json.loads(p.read_text(encoding="utf-8")), p.stem)
        findings = [f for f in scan(tools) if f.severity != "low"]
        names = {f.tool for f in findings}
        flagged += len(names)
        total += len(tools)
        rules.update(f.rule for f in findings)
        if show:
            for f in findings:
                print(f"  real {f.rule} {f.server}/{f.tool}: {f.message} > {f.excerpt}")
    res["third_party"] = {"tools": total, "flagged": flagged, "by_rule": dict(rules)}
    print(json.dumps(res, indent=2))
    (root / "reports" / "evaluation.json").write_text(json.dumps(res, indent=2) + "\n")


if __name__ == "__main__":
    main()
