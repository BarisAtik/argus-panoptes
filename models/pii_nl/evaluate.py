"""Score redactors on generated documents.

A leak is a word of a personal value that stays readable. Intervals resample templates, because
those are the independent unit here: fifty fills of one sentence are not fifty observations.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable, Sequence

import numpy as np

from forge.stats import ratio_ci_t

from .generate import Document, Span

WORD = re.compile(r"[^\W_]+", re.UNICODE)
Redactor = Callable[[str], Sequence[tuple[int, int]]]


def _covered(start: int, end: int, masks: Sequence[tuple[int, int]]) -> bool:
    return any(a < end and start < b for a, b in masks)


def span_leaked(text: str, span: Span, masks: Sequence[tuple[int, int]]) -> bool:
    """True if any word inside the value is untouched. `S. Bakker` with `S.` kept is a leak."""
    for match in WORD.finditer(text, span.start, span.end):
        if not _covered(match.start(), match.end(), masks):
            return True
    return False


def score_document(doc: Document, masks: Sequence[tuple[int, int]]) -> dict:
    """Counts per kind, plus masked and total words outside any annotated value."""
    leaks: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for span in doc.spans:
        if span.kind in (None, "AFLEIDER"):
            continue
        row = leaks[span.kind]
        row[0] += int(span_leaked(doc.text, span, masks))
        row[1] += 1
    outside_masked = outside_total = distractor_masked = distractor_total = 0
    neutral = [s for s in doc.spans if s.kind is None]
    gold = [s for s in doc.spans if s.kind not in (None, "AFLEIDER")]
    distractors = [s for s in doc.spans if s.kind == "AFLEIDER"]
    for match in WORD.finditer(doc.text):
        a, b = match.start(), match.end()
        if any(s.start < b and a < s.end for s in gold + neutral):
            continue
        masked = _covered(a, b, masks)
        if any(s.start < b and a < s.end for s in distractors):
            distractor_total += 1
            distractor_masked += int(masked)
        else:
            outside_total += 1
            outside_masked += int(masked)
    return {
        "leaks": dict(leaks),
        "outside": (outside_masked, outside_total),
        "distractor": (distractor_masked, distractor_total),
    }


def evaluate(docs: Sequence[Document], redactor: Redactor) -> list[dict]:
    """One row per document and kind, ready for `summarise`."""
    rows = []
    for doc in docs:
        result = score_document(doc, list(redactor(doc.text)))
        base = {
            "template": doc.template,
            "register": doc.register,
            "group": doc.group,
            "repeat": doc.repeat,
        }
        for kind, (leaked, total) in result["leaks"].items():
            rows.append({**base, "kind": kind, "leaked": leaked, "total": total})
        rows.append(
            {**base, "kind": "_outside", "leaked": result["outside"][0],
             "total": result["outside"][1]}
        )
        rows.append(
            {**base, "kind": "_distractor", "leaked": result["distractor"][0],
             "total": result["distractor"][1]}
        )
    return rows


def rate(rows: Sequence[dict], cluster: str = "template", **where) -> dict:
    """Pooled rate with a cluster t interval. `kind=None` means every personal-data kind."""
    chosen = [
        r
        for r in rows
        if all(
            (not r["kind"].startswith("_")) if (k == "kind" and v is None) else r[k] == v
            for k, v in where.items()
        )
    ]
    if not chosen:
        return {"rate": float("nan"), "low": float("nan"), "high": float("nan"), "n": 0}
    leaked = np.array([r["leaked"] for r in chosen], dtype=float)
    total = np.array([r["total"] for r in chosen], dtype=float)
    ids = [r[cluster] for r in chosen]
    n_clusters = len(set(ids))
    estimate = float(leaked.sum() / max(total.sum(), 1))
    if n_clusters < 3:
        return {"rate": estimate, "low": None, "high": None, "n": int(total.sum()),
                "clusters": n_clusters}
    ci = ratio_ci_t(leaked, total, ids)
    return {"rate": estimate, "low": float(ci.low), "high": float(ci.high),
            "n": int(total.sum()), "clusters": n_clusters}
