"""Static checks for A2A Agent Cards.

Structural on purpose. mcp-lens scored 100% on its dev set and 5 to 8% on fresh adversarial holdouts when text rules
were asked to find injections, so this only reports facts about a card that a rewrite cannot hide. A clean result
means the card is well-formed, not that it is honest: a signed, tidy, lying card passes.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

MAX_DESCRIPTION = 600


@dataclass
class Finding:
    rule: str
    severity: str
    message: str
    where: str = ""


def _hidden(text: str) -> list[str]:
    return sorted({f"U+{ord(c):04X}" for c in text if unicodedata.category(c) in ("Cf", "Co", "Cn") and c != "\n"})


def _loopback(host: str) -> bool:
    return host in ("localhost", "127.0.0.1", "::1") or host.endswith(".test")


def lint(card: dict[str, Any]) -> list[Finding]:
    f: list[Finding] = []
    if not card.get("signatures"):
        f.append(Finding("unsigned", "high", "No signature, so origin and integrity cannot be checked."))
    schemes, reqs = card.get("securitySchemes") or {}, card.get("securityRequirements") or []
    if not schemes and not reqs:
        f.append(Finding("no-auth", "high", "No security scheme declared. Anyone who can reach it can send tasks."))
    for i, iface in enumerate(card.get("supportedInterfaces") or []):
        url = urlsplit(iface.get("url", ""))
        if url.scheme != "https" and not _loopback(url.hostname or ""):
            f.append(Finding("plain-http", "high", f"Interface {i} is not HTTPS.", url.geturl()))
    caps = card.get("capabilities") or {}
    if caps.get("pushNotifications") and not schemes:
        f.append(Finding("push-unauthenticated", "high", "Push callbacks without auth: a caller picks where results go."))
    texts = [("description", card.get("description", ""))]
    skills = card.get("skills") or []
    for s in skills:
        texts += [(f"skill {s.get('id')}", s.get("description", ""))]
        texts += [(f"skill {s.get('id')} example", e) for e in s.get("examples") or []]
    for where, text in texts:
        if hidden := _hidden(text):
            f.append(Finding("hidden-characters", "high", f"Invisible characters: {', '.join(hidden[:5])}.", where))
        if len(text) > MAX_DESCRIPTION:
            f.append(Finding("long-text", "medium", f"{len(text)} characters goes to a planner verbatim.", where))
        if re.search(r"https?://", text):
            f.append(Finding("url-in-text", "medium", "A URL in free text can steer a planner.", where))
    if not skills:
        f.append(Finding("no-skills", "medium", "No declared skills, so a capability map has nothing to check."))
    ids = [s.get("id") for s in skills]
    if len(ids) != len(set(ids)):
        f.append(Finding("duplicate-skill", "medium", "Two skills share an id."))
    if not card.get("provider"):
        f.append(Finding("no-provider", "low", "No provider recorded."))
    return f


def sarif(path: str, findings: list[Finding]) -> dict[str, Any]:
    level = {"high": "error", "medium": "warning", "low": "note"}
    return {"version": "2.1.0", "runs": [{"tool": {"driver": {"name": "hermes-card-lint"}}, "results": [
        {"ruleId": x.rule, "level": level[x.severity], "message": {"text": f"{x.message} {x.where}".strip()},
         "locations": [{"physicalLocation": {"artifactLocation": {"uri": path}}}]} for x in findings]}]}


def lint_file(path: str | Path) -> list[Finding]:
    return lint(json.loads(Path(path).read_text(encoding="utf-8")))
