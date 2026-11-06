"""Audit a live index: will the mapping let Sigma rules fire?

Read-only. It reads the mapping and a sample of events and reports the failures measured in this
project. Everything it warns about is silent on the engine: no error, just no alerts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .engine import IGNORE_ABOVE_SAFE, Engine
from .readiness import Inventory, check
from .rules import Rule

KEY_FIELDS = (
    "Channel",
    "EventID",
    "Image",
    "CommandLine",
    "ParentImage",
    "ParentCommandLine",
    "TargetObject",
    "TargetFilename",
    "ScriptBlockText",
    "IpAddress",
)
LONG_FIELDS = ("CommandLine", "ParentCommandLine", "ScriptBlockText")


@dataclass
class Finding:
    field: str
    severity: str
    problem: str


def _leaf(properties: dict[str, Any], dotted: str) -> dict[str, Any] | None:
    node: dict[str, Any] = {"properties": properties}
    for part in dotted.split("."):
        node = (node.get("properties") or {}).get(part)
        if node is None:
            return None
    return node


def audit_mapping(properties: dict[str, Any], normalizers: dict[str, Any]) -> list[Finding]:
    findings = []
    for name in KEY_FIELDS:
        field = _leaf(properties, name)
        if field is None:
            findings.append(Finding(name, "info", "not mapped: no event has set it yet"))
            continue
        kind = field.get("type", "object")
        if kind == "text":
            findings.append(
                Finding(
                    name,
                    "high",
                    "analysed text: a wildcard is compared with single tokens, so "
                    "`*\\cmd.exe` and anything spanning a separator cannot match",
                )
            )
        elif kind == "keyword":
            if not _lowercases(field.get("normalizer"), normalizers) and name != "EventID":
                findings.append(
                    Finding(
                        name,
                        "high",
                        "keyword without a lowercase normalizer: rules are "
                        "case-insensitive by design, and the field is not",
                    )
                )
            limit = field.get("ignore_above", 2147483647)
            if name in LONG_FIELDS and limit <= IGNORE_ABOVE_SAFE:
                findings.append(
                    Finding(
                        name,
                        "medium",
                        f"ignore_above={limit}: longer values are stored "
                        "but not searchable, and long scripts are what rules look for. "
                        "Fine if values are chunked at ingest",
                    )
                )
        elif kind == "wildcard":
            findings.append(
                Finding(
                    name,
                    "medium",
                    "wildcard field: fired on few rules through query_string "
                    "on OpenSearch 3.9. Test it on your engine before relying on it",
                )
            )
    return findings


def _lowercases(name: str | None, normalizers: dict[str, Any]) -> bool:
    if not name:
        return False
    return "lowercase" in (normalizers.get(name, {}).get("filter") or [])


def audit_index(engine: Engine, index: str) -> list[Finding]:
    response = engine.client.get(f"/{index}").raise_for_status().json()
    body = next(iter(response.values()))
    settings = body["settings"]["index"]
    normalizers = (settings.get("analysis") or {}).get("normalizer") or {}
    return audit_mapping(body["mappings"].get("properties", {}), normalizers)


def _agg_field(properties: dict[str, Any], name: str) -> str:
    field = properties.get(name, {})
    return f"{name}.keyword" if field.get("type") == "text" else name


def sample_inventory(engine: Engine, index: str, per_source: int = 25) -> Inventory:
    """Sample each channel and event id. A flat sample would miss rare sources entirely."""
    mapping = engine.client.get(f"/{index}/_mapping").raise_for_status().json()
    properties = next(iter(mapping.values()))["mappings"].get("properties", {})
    body = {
        "size": 0,
        "aggs": {
            "channels": {
                "terms": {"field": _agg_field(properties, "Channel"), "size": 200},
                "aggs": {
                    "ids": {
                        "terms": {"field": _agg_field(properties, "EventID"), "size": 300},
                        "aggs": {"sample": {"top_hits": {"size": per_source}}},
                    }
                },
            }
        },
    }
    response = engine.client.post(f"/{index}/_search", json=body).raise_for_status().json()
    inventory = Inventory()
    for channel in response["aggregations"]["channels"]["buckets"]:
        for event_id in channel["ids"]["buckets"]:
            for hit in event_id["sample"]["hits"]["hits"]:
                inventory.add({key: _flat(value) for key, value in hit["_source"].items()})
    return inventory


def _flat(value: Any) -> str:
    return value[0] if isinstance(value, list) and value else str(value)


def readiness_table(rules: list[Rule], inventory: Inventory) -> dict[str, list[str]]:
    table: dict[str, list[str]] = {}
    for rule in rules:
        verdict = check(rule.sigma, inventory)
        table.setdefault(verdict.status, []).append(rule.title)
    return table
