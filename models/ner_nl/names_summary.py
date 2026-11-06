"""Summarise runs/ner_nl/names.csv in Python; `names_mixed.R` cross-checks with a mixed model."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from forge.stats import _cluster_sums, _weights

OUT = Path("runs/ner_nl")


def _gap(by_doc: dict, group: str, reference: str, seed: int = 0, n_boot: int = 5000) -> tuple:
    docs = sorted(by_doc)
    a = np.array([by_doc[d][group] for d in docs], dtype=float)
    b = np.array([by_doc[d][reference] for d in docs], dtype=float)
    # columns: hits, total. Same mentions per article in every group.
    sa, sb = _cluster_sums(a, None), _cluster_sums(b, None)
    w = _weights(len(docs), n_boot, np.random.default_rng(seed))
    ra = (w @ sa)[:, 0] / (w @ sa)[:, 1]
    rb = (w @ sb)[:, 0] / (w @ sb)[:, 1]
    low, high = np.quantile(ra - rb, [0.025, 0.975])
    return float(low), float(high)


def summarise(rows: list[dict], metric: str = "exact", reference: str = "dutch") -> list[dict]:
    by = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: [0, 0])))
    for r in rows:
        cell = by[r["model"]][r["doc"]][r["group"]]
        cell[0] += int(r[metric])
        cell[1] += 1
    out = []
    for model, docs in by.items():
        groups = sorted({g for d in docs.values() for g in d})
        totals = {g: np.sum([d[g] for d in docs.values()], axis=0) for g in groups}
        for group in groups:
            hits, n = totals[group]
            row = {
                "model": model,
                "metric": metric,
                "group": group,
                "recall": float(hits / n),
                "mentions": int(n),
            }
            if group != reference:
                low, high = _gap(docs, group, reference)
                row["gap_vs_ref"] = float(hits / n - totals[reference][0] / totals[reference][1])
                row["gap_low"], row["gap_high"] = low, high
            out.append(row)
    return out


def main() -> None:
    with open(OUT / "names.csv", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    summary = summarise(rows, "exact") + summarise(rows, "any_overlap")
    (OUT / "names_summary.json").write_text(json.dumps(summary, indent=2))
    for row in summary:
        print(row)


if __name__ == "__main__":
    main()
