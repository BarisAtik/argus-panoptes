"""Load Sigma rules with the metadata that the evaluation needs."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from sigma.collection import SigmaCollection
from sigma.rule import SigmaRule

TECHNIQUE = re.compile(r"^attack\.(t\d{4}(?:\.\d{3})?)$", re.IGNORECASE)


@dataclass
class Rule:
    id: str
    title: str
    path: str
    status: str
    level: str
    created: str
    author: str = ""  # DRL 1.1: messages based on a match must keep this
    techniques: list[str] = field(default_factory=list)
    sigma: SigmaRule | None = field(default=None, repr=False)


def _iso(value: object) -> str:
    return value.isoformat() if isinstance(value, date) else str(value or "")


def techniques_of(rule: SigmaRule) -> list[str]:
    found = []
    for tag in rule.tags:
        match = TECHNIQUE.match(f"{tag.namespace}.{tag.name}")
        if match:
            found.append(match.group(1).upper())
    return sorted(set(found))


def from_sigma(rule: SigmaRule, path: str = "") -> Rule:
    return Rule(
        id=str(rule.id),
        title=rule.title,
        path=path,
        status=str(rule.status.name).lower() if rule.status else "none",
        level=str(rule.level.name).lower() if rule.level else "none",
        created=_iso(rule.date),
        author=rule.author or "",
        techniques=techniques_of(rule),
        sigma=rule,
    )


def parse_rule(text: str, path: str = "") -> Rule | None:
    """Skip correlation rules and anything that does not parse. Callers count the difference."""
    collection = SigmaCollection.from_yaml(text, collect_errors=True)
    for item in collection.rules:
        if isinstance(item, SigmaRule) and not item.errors:
            return from_sigma(item, path)
    return None


def load_rules(*roots: Path) -> tuple[list[Rule], list[str]]:
    """Returns rules, sorted by path, and the paths that could not be used."""
    rules, skipped = [], []
    for root in roots:
        for path in sorted(root.rglob("*.yml")):
            parsed = parse_rule(path.read_text(encoding="utf-8"), str(path))
            if parsed is None:
                skipped.append(str(path))
            else:
                rules.append(parsed)
    return rules, skipped
