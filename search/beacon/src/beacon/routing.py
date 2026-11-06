"""Decide how much BM25 to trust for a query, which depends on whether it can match at all.

A Dutch stemmer over a Dutch index cannot match an English query, yet RRF gives both lists the
same weight, so BM25's accidental hits push good dense results down. Two ways to notice:

* `lang`: detect the language of the query. Word frequencies from `wordfreq` decide.
* `coverage`: the share of query terms found in the index. No language model, and it works for
  any language. It also knows about the terms of this collection, like `algoritmeregister`.
"""

from __future__ import annotations

from collections.abc import Callable

from .text import _TOKEN


def detect_dutch(query: str, lookup: Callable[[str, str], float] | None = None) -> bool:
    """True if a query looks more Dutch than anything else on the list."""
    if lookup is None:
        from wordfreq import zipf_frequency as lookup
    words = _TOKEN.findall(query.lower())
    if not words:
        return True
    languages = ("nl", "en", "de", "fr", "es")
    totals = {lang: sum(lookup(word, lang) for word in words) for lang in languages}
    return totals["nl"] >= max(totals.values())


def lexical_weight(
    query: str, method: str, coverage: Callable[[str], float], power: float = 1.0
) -> float:
    """Weight between 0 and 1 for the lexical list."""
    if method == "none":
        return 1.0
    if method == "lang":
        return 1.0 if detect_dutch(query) else 0.0
    if method == "coverage":
        return coverage(query) ** power
    raise ValueError(f"unknown routing method {method!r}")
