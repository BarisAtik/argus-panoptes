from nightwatch.readiness import build_inventory, check, source_of
from nightwatch.rules import parse_rule

HEAD = """
title: T
id: 33333333-3333-4333-8333-333333333333
logsource:
  product: windows
  {source}
detection:
{detection}
"""


def rule(detection, source="category: process_creation"):
    return parse_rule(HEAD.format(source=source, detection=detection)).sigma


SYSMON = "Microsoft-Windows-Sysmon/Operational"
SELECT = "  selection:\n    Image: a\n  condition: selection"


def test_sources():
    assert source_of(rule(SELECT)) == ([SYSMON.lower()], ["1"])
    assert source_of(rule(SELECT, "service: security")) == (["security"], [])
    channels, ids = source_of(rule(SELECT, "category: ps_script"))
    assert ids == ["4104"] and len(channels) == 2
    assert source_of(rule(SELECT, "service: nothing-known")) == ([], [])


def inventory(**fields):
    return build_inventory([{"Channel": SYSMON, "EventID": "1", **fields}])


def test_ready(rule=rule):
    assert check(rule(SELECT), inventory(Image="x")).status == "ready"


def test_no_source():
    assert check(rule(SELECT, "category: dns_query"), inventory(Image="x")).status == "no_source"


def test_channel_case_is_ignored():
    logs = build_inventory([{"Channel": "security", "EventID": "1", "Image": "x"}])
    assert check(rule(SELECT, "service: security"), logs).status == "ready"


def test_missing_field_is_named():
    verdict = check(rule(SELECT), inventory(Other="x"))
    assert verdict.status == "no_field" and verdict.missing == ["Image"]


def test_placeholder_value_is_not_a_value():
    assert check(rule(SELECT), inventory(Image="-")).status == "no_field"


def test_negated_field_does_not_block():
    text = (
        "  selection:\n    Image: a\n  filter:\n    User: b\n  condition: selection and not filter"
    )
    assert check(rule(text), inventory(Image="x")).status == "ready"


def test_one_live_branch_is_enough():
    text = "  a:\n    Image: x\n  b:\n    Nope: y\n  condition: 1 of them"
    assert check(rule(text), inventory(Image="x")).status == "ready"
    both = "  a:\n    Image: x\n  b:\n    Nope: y\n  condition: all of them"
    assert check(rule(both), inventory(Image="x")).status == "no_field"


def test_null_test_needs_no_field():
    text = "  selection:\n    Image: x\n    Missing: null\n  condition: selection"
    assert check(rule(text), inventory(Image="x")).status == "ready"
