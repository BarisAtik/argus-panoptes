"""Load manifests, run rules, pin tool definitions, write SARIF."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import __version__
from .rules import RULE_DOCS, SEVERITY, Finding, Tool, scan_set, scan_tool


def load_manifest(data: Any, default_server: str = "server") -> list[Tool]:
    """Accepts a tools/list result, a bare tool list, or {servers: {name: {tools}}}."""
    if isinstance(data, dict) and "servers" in data:
        out: list[Tool] = []
        for name, body in data["servers"].items():
            out += load_manifest(body, name)
        return out
    server = default_server
    if isinstance(data, dict):
        server = data.get("server", server)
        tools = data.get("tools", [])
    else:
        tools = data
    return [
        Tool(server, t["name"], t.get("description") or "", t.get("inputSchema") or t.get("input_schema") or {})
        for t in tools
    ]


def scan(tools: list[Tool]) -> list[Finding]:
    known = {t.name for t in tools}
    findings: list[Finding] = []
    for t in tools:
        findings += scan_tool(t, known)
    findings += scan_set(tools)
    return sorted(set(findings), key=lambda f: (-SEVERITY[f.severity], f.rule, f.server, f.tool, f.field))


def fingerprint(t: Tool) -> str:
    canon = json.dumps({"d": t.description, "s": t.schema}, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canon.encode()).hexdigest()


def make_lock(tools: list[Tool]) -> dict[str, Any]:
    return {"version": 1, "tools": {f"{t.server}/{t.name}": fingerprint(t) for t in tools}}


def diff_lock(tools: list[Tool], lock: dict[str, Any]) -> list[Finding]:
    now = make_lock(tools)["tools"]
    old = lock.get("tools", {})
    out = []
    for key, val in now.items():
        server, _, name = key.partition("/")
        if key not in old:
            out.append(Finding("ML015", "medium", server, name, "lock", "tool is new since the lock file"))
        elif old[key] != val:
            out.append(Finding("ML015", "high", server, name, "lock", "tool definition changed since it was pinned"))
    for key in old.keys() - now.keys():
        server, _, name = key.partition("/")
        out.append(Finding("ML015", "low", server, name, "lock", "tool was removed since the lock file"))
    return out


def to_sarif(findings: list[Finding], artifact: str) -> dict[str, Any]:
    level = {"high": "error", "medium": "warning", "low": "note"}
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {
                "name": "mcp-lens", "version": __version__,
                "rules": [{"id": k, "shortDescription": {"text": v}} for k, v in sorted(RULE_DOCS.items())],
            }},
            "results": [{
                "ruleId": f.rule, "level": level[f.severity],
                "message": {"text": f"{f.server}/{f.tool} [{f.field}]: {f.message}"},
                "locations": [{"physicalLocation": {"artifactLocation": {"uri": artifact}}}],
            } for f in findings],
        }],
    }


@dataclass
class Metrics:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0


def is_flagged(findings: list[Finding], threshold: str = "medium") -> bool:
    return any(SEVERITY[f.severity] >= SEVERITY[threshold] for f in findings)


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))
