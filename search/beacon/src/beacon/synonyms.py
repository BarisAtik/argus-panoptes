"""Known synonyms for the BM25 query. Dense search does not need them.

Each group lists terms that mean the same thing in this domain. A query that contains one gets
the others added, and BM25's OR semantics do the rest. Terms stay in a plain list so that a client
can review them, which beats a model that guesses. Replace this list for another domain.
"""

from __future__ import annotations

import re

GROUPS: tuple[tuple[str, ...], ...] = (
    ("dpia", "gegevensbeschermingseffectbeoordeling", "data protection impact assessment",
     "pia", "privacy impact assessment"),
    ("iama", "impact assessment mensenrechten en algoritmes"),
    ("fria", "fundamental rights impact assessment", "grondrechteneffectbeoordeling"),
    ("avg", "gdpr", "algemene verordening gegevensbescherming"),
    ("ai-verordening", "ai act", "aia", "verordening artificiële intelligentie"),
    ("bio", "baseline informatiebeveiliging overheid"),
    ("woo", "wet open overheid"),
    ("awb", "algemene wet bestuursrecht"),
    ("awgb", "algemene wet gelijke behandeling"),
    ("gebruiksverantwoordelijke", "deployer"),
    ("aanbieder", "provider"),
    ("wcag", "digitale toegankelijkheid"),
)  # fmt: skip


def _pattern(term: str) -> re.Pattern:
    return re.compile(rf"(?<![\w-]){re.escape(term)}(?![\w-])", re.IGNORECASE)


_COMPILED = [[(term, _pattern(term)) for term in group] for group in GROUPS]


def expand(query: str) -> str:
    """The query plus the synonyms of any term it contains."""
    extra: list[str] = []
    for group in _COMPILED:
        if any(pattern.search(query) for _, pattern in group):
            extra += [term for term, pattern in group if not pattern.search(query)]
    return " ".join([query, *extra])
