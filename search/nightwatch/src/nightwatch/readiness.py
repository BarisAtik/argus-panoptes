"""Can this rule fire at all on these logs?

A rule that needs a field or a log source you do not collect returns nothing, forever, and looks
exactly like a rule with nothing to report. This check needs no attack data: it compares what each
rule requires with what the logs contain. It only says a rule is *able* to fire.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from sigma.conditions import (
    ConditionAND,
    ConditionFieldEqualsValueExpression,
    ConditionNOT,
    ConditionOR,
)
from sigma.pipelines.common import windows_logsource_mapping
from sigma.pipelines.sysmon.sysmon import sysmon_generic_logsource_eventid_mapping
from sigma.pipelines.windows.windows import windows_generic_category_channel_mapping
from sigma.rule import SigmaRule
from sigma.types import SigmaExpansion, SigmaNull

PLACEHOLDERS = {"", "-", "n/a", "none"}
SKIP_FIELDS = {"case_id", "dataset_id", "split"}
SYSMON_CHANNEL = "microsoft-windows-sysmon/operational"


@dataclass
class Inventory:
    """Fields with at least one real value, per channel and event id. Case-folded channel."""

    by_source: dict[tuple[str, str], set[str]] = field(default_factory=lambda: defaultdict(set))
    by_channel: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))

    def add(self, event: dict[str, str]) -> None:
        channel = event.get("Channel", "").lower()
        event_id = event.get("EventID", "")
        fields = {
            name
            for name, value in event.items()
            if name not in SKIP_FIELDS and value.strip().lower() not in PLACEHOLDERS
        }
        self.by_source[(channel, event_id)] |= fields
        self.by_channel[channel] |= fields


def build_inventory(events: Iterable[dict[str, str]]) -> Inventory:
    inventory = Inventory()
    for event in events:
        inventory.add(event)
    return inventory


def _channels(service: str) -> list[str]:
    channels = windows_logsource_mapping[service]
    return [c.lower() for c in ([channels] if isinstance(channels, str) else channels)]


def source_of(rule: SigmaRule) -> tuple[list[str], list[str]]:
    """Channels and event ids a rule reads. No channels means the rule does not say."""
    source = rule.logsource
    category = source.category or ""
    if category in sysmon_generic_logsource_eventid_mapping:
        ids = sysmon_generic_logsource_eventid_mapping[category]
        ids = ids if isinstance(ids, list) else [ids]
        return [SYSMON_CHANNEL], [str(item) for item in ids]
    if category in windows_generic_category_channel_mapping:
        info = windows_generic_category_channel_mapping[category]
        return _channels(info["service"]), [str(info["EventID"])]
    if source.service and source.service in windows_logsource_mapping:
        return _channels(source.service), []
    return [], []


def _absence_test(node: ConditionFieldEqualsValueExpression) -> bool:
    value = node.value
    if isinstance(value, SigmaExpansion):
        return False
    return isinstance(value, SigmaNull) or type(value).__name__ == "SigmaExists" and not value


def _missing(node, present: set[str]) -> set[str] | None:
    """Fields that stop this node from ever being true, or None when it can be true."""
    if isinstance(node, ConditionNOT):
        return None  # an absent field cannot make a negated branch false
    if isinstance(node, ConditionAND):
        parts = [_missing(arg, present) for arg in node.args]
        lost = {name for part in parts if part for name in part}
        return lost or None
    if isinstance(node, ConditionOR):
        parts = [_missing(arg, present) for arg in node.args]
        if any(part is None for part in parts):
            return None
        return {name for part in parts if part for name in part}
    if isinstance(node, ConditionFieldEqualsValueExpression):
        if node.field in present or _absence_test(node):
            return None
        return {node.field}
    return None  # keyword searches run over everything


@dataclass
class Verdict:
    status: str  # ready | no_source | no_field | unknown_source
    missing: list[str] = field(default_factory=list)


def check(rule: SigmaRule, inventory: Inventory) -> Verdict:
    channels, ids = source_of(rule)
    if not channels:
        return Verdict("unknown_source")
    if ids:
        sources = [inventory.by_source.get((c, item)) for c in channels for item in ids]
    else:
        sources = [inventory.by_channel.get(c) for c in channels]
    if all(fields is None for fields in sources):
        return Verdict("no_source")
    present = {name for fields in sources if fields for name in fields}
    lost: set[str] = set()
    for condition in rule.detection.parsed_condition:
        missing = _missing(condition.parsed, present)
        if missing is None:
            return Verdict("ready")
        lost |= missing
    return Verdict("no_field", sorted(lost))
