"""Data quality report for a corpus: what would quietly distort search results?"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from datetime import date

from .models import Document

_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_IBAN = re.compile(r"\bNL\d{2}\s?[A-Z]{4}(?:\s?\d{4}){2}\s?\d{2}\b")
_PHONE = re.compile(r"(?<![\w.-])(?:\+31|0031|0)[ -]?(?:6[ -]?\d{8}|\d{2,3}[ -]?\d{6,7})(?![\w-])")
_NINE_DIGITS = re.compile(r"(?<![\d.-])\d{9}(?![\d-])")
_PSEUDONYM = re.compile(r"\[[a-zA-Z][^\]\n]{1,40}\]")


def is_bsn_like(number: str) -> bool:
    """The Dutch 11-test. Many nine-digit case numbers pass by chance, so this is only a hint."""
    if len(number) != 9 or not number.isdigit() or number == "000000000":
        return False
    weights = (9, 8, 7, 6, 5, 4, 3, 2, -1)
    return sum(int(d) * w for d, w in zip(number, weights, strict=True)) % 11 == 0


def identifier_hints(text: str) -> Counter:
    """Count identifier-shaped strings. Reports counts only, so the report holds no such value."""
    hints: Counter = Counter()
    hints["email"] = len(_EMAIL.findall(text))
    hints["iban"] = len(_IBAN.findall(text))
    hints["phone"] = len(_PHONE.findall(text))
    hints["bsn_shaped"] = sum(is_bsn_like(n) for n in _NINE_DIGITS.findall(text))
    return +hints


def _fingerprint(text: str) -> str:
    return hashlib.sha256(" ".join(text.lower().split()).encode()).hexdigest()


def _percentile(values: list[int], q: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def report(documents: list[Document], today: date | None = None, short_words: int = 50) -> dict:
    today_text = (today or date.today()).isoformat()
    lengths = [len(d.text.split()) for d in documents]
    fingerprints = Counter(_fingerprint(d.text) for d in documents if d.text.strip())
    ids = Counter(d.id for d in documents)
    hints: Counter = Counter()
    documents_with_hints = 0
    pseudonyms = 0
    for document in documents:
        found = identifier_hints(document.text)
        hints.update(found)
        documents_with_hints += bool(found)
        pseudonyms += len(_PSEUDONYM.findall(document.text))

    return {
        "documents": len(documents),
        "date_range": [
            min((d.date for d in documents if d.date), default=None),
            max((d.date for d in documents if d.date), default=None),
        ],
        "words": {
            "total": sum(lengths),
            "p10": _percentile(lengths, 0.10),
            "median": _percentile(lengths, 0.50),
            "p90": _percentile(lengths, 0.90),
        },
        "issues": {
            "duplicate_ids": sum(c - 1 for c in ids.values() if c > 1),
            "duplicate_texts": sum(c - 1 for c in fingerprints.values() if c > 1),
            "empty_body": sum(1 for n in lengths if n == 0),
            f"short_body_under_{short_words}_words": sum(1 for n in lengths if 0 < n < short_words),
            "missing_summary": sum(1 for d in documents if not d.summary),
            "missing_date": sum(1 for d in documents if not d.date),
            "future_date": sum(1 for d in documents if d.date and d.date > today_text),
            "missing_court": sum(1 for d in documents if not d.court),
            "missing_subject": sum(1 for d in documents if not d.subjects),
        },
        "privacy": {
            "pseudonym_markers": pseudonyms,
            "documents_with_identifier_hints": documents_with_hints,
            "identifier_hints": dict(hints),
        },
        "top_courts": Counter(d.court or "(none)" for d in documents).most_common(10),
        "top_subjects": Counter(s for d in documents for s in d.subjects).most_common(10),
    }


def to_markdown(result: dict) -> str:
    lines = [
        "# Data quality report",
        "",
        f"- Documents: {result['documents']}",
        f"- Date range: {result['date_range'][0]} to {result['date_range'][1]}",
        "- Words per document: median {median}, p10 {p10}, p90 {p90}, total {total}".format(
            **result["words"]
        ),
        "",
        "## Issues",
        "",
        "| Check | Count |",
        "| --- | --- |",
    ]
    lines += [f"| {key} | {value} |" for key, value in result["issues"].items()]
    lines += ["", "## Privacy signals", "", "| Check | Count |", "| --- | --- |"]
    privacy = result["privacy"]
    lines.append(f"| pseudonym markers | {privacy['pseudonym_markers']} |")
    flagged = privacy["documents_with_identifier_hints"]
    lines.append(f"| documents with identifier hints | {flagged} |")
    lines += [f"| hint: {key} | {value} |" for key, value in privacy["identifier_hints"].items()]
    lines += [
        "",
        "Hints are pattern matches and need human review. A clean result does not prove",
        "that a text holds no personal data.",
        "",
        "## Coverage",
        "",
    ]
    lines += [f"- Court: {name}: {count}" for name, count in result["top_courts"]]
    lines += [f"- Subject: {name}: {count}" for name, count in result["top_subjects"]]
    return "\n".join(lines) + "\n"
