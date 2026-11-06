"""Find citations of laws in text, and reduce each to one canonical form.

`artikel 22 AVG`, `art. 22 GDPR` and `Article 22 of the General Data Protection Regulation` all
become `avg:22`. A law named without an article gives `avg`. The same code reads source pages and
queries, so a page's reference list can be matched exactly without putting it in the indexed text.
"""

from __future__ import annotations

import re

# Canonical name, then every spelling. Longest spellings are tried first.
LAWS: dict[str, tuple[str, ...]] = {
    "avg": (
        "algemene verordening gegevensbescherming", "general data protection regulation",
        "avg", "gdpr",
    ),
    "aia": (
        "verordening artificiële intelligentie", "verordening artificiele intelligentie",
        "artificial intelligence act", "ai-verordening", "ai verordening", "aiverordening",
        "ai act", "ai-act", "aia", "2024/1689",
    ),
    "awb": ("algemene wet bestuursrecht", "awb"),
    "awgb": ("algemene wet gelijke behandeling", "awgb"),
    "woo": ("wet open overheid", "woo"),
    "archiefwet": ("archiefwet",),
    "auteurswet": ("auteurswet",),
    "grondwet": ("grondwet",),
    "evrm": ("europees verdrag voor de rechten van de mens", "evrm", "echr"),
    "handvest": ("handvest van de grondrechten", "handvest"),
    "wdo": ("wet digitale overheid", "wdo"),
}  # fmt: skip

_SPELLINGS = sorted(
    ((spelling, law) for law, names in LAWS.items() for spelling in names),
    key=lambda item: -len(item[0]),
)
_BY_SPELLING = dict(_SPELLINGS)
_LAW = "|".join(re.escape(spelling) for spelling, _ in _SPELLINGS)
_NUMBER = r"\d+[a-z]?(?::\d+[a-z]?)?"
_MARK = r"(?:artikelen|artikel|articles|article|artt?\.?)"
# What may stand between an article number and the law: `(1 sub d)`, `lid 1 onder c`, `van de`.
_GAP = (
    r"(?:\([^)]{0,20}\)|,|\blid\b|\bleden\b|\bsub\b|\bonder\b|\btot en met\b|\bvan\b"
    r"|\bde\b|\bof\b|\bthe\b|\bhet\b|\b[a-z]\b|\b\d+\b|\s)*?"
)
_ARTICLE_THEN_LAW = re.compile(
    rf"\b{_MARK}\s*(?P<first>{_NUMBER})(?:\s*(?:-|–|t/m|tot en met|en|and)\s*(?P<last>{_NUMBER}))?"
    rf"{_GAP}\s*(?P<law>{_LAW})(?![\w-])",
    re.IGNORECASE,
)
_LAW_THEN_ARTICLE = re.compile(
    rf"(?<![\w-])(?P<law>{_LAW})\s*,?\s*{_MARK}\s*(?P<first>{_NUMBER})", re.IGNORECASE
)
_LAW_ONLY = re.compile(rf"(?<![\w-])(?P<law>{_LAW})(?![\w-])", re.IGNORECASE)
MAX_RANGE = 30


def _article_keys(law: str, first: str, last: str | None) -> list[str]:
    first, last = first.lower(), (last or "").lower()
    if last and first.isdigit() and last.isdigit() and 0 < int(last) - int(first) <= MAX_RANGE:
        return [f"{law}:{number}" for number in range(int(first), int(last) + 1)]
    return [f"{law}:{first}"] + ([f"{law}:{last}"] if last else [])


def extract_refs(text: str) -> list[str]:
    """Canonical citations in a text, sorted. Both `avg` and `avg:22` for `artikel 22 AVG`."""
    found: set[str] = set()
    for pattern in (_ARTICLE_THEN_LAW, _LAW_THEN_ARTICLE):
        for match in pattern.finditer(text):
            law = _BY_SPELLING[match["law"].lower()]
            found.add(law)
            found.update(_article_keys(law, match["first"], match.groupdict().get("last")))
    for match in _LAW_ONLY.finditer(text):
        found.add(_BY_SPELLING[match["law"].lower()])
    return sorted(found)


def article_refs(refs: list[str]) -> list[str]:
    """Only the citations that name an article."""
    return [ref for ref in refs if ":" in ref]
