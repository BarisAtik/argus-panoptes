import pytest

from nightwatch.audit import audit_index, audit_mapping, readiness_table, sample_inventory


def problems(properties, normalizers=None):
    return {(f.field, f.severity) for f in audit_mapping(properties, normalizers or {})}


def test_text_field_is_high():
    assert ("Image", "high") in problems({"Image": {"type": "text"}})


def test_raw_keyword_is_high_but_eventid_is_fine():
    found = problems({"Image": {"type": "keyword"}, "EventID": {"type": "keyword"}})
    assert ("Image", "high") in found and ("EventID", "high") not in found


def test_lower_keyword_passes():
    field = {"type": "keyword", "normalizer": "lower"}
    found = problems({"Image": field}, {"lower": {"filter": ["lowercase"]}})
    assert ("Image", "high") not in found


def test_short_ignore_above_on_long_field():
    field = {"type": "keyword", "normalizer": "lower", "ignore_above": 1024}
    found = problems({"CommandLine": field}, {"lower": {"filter": ["lowercase"]}})
    assert ("CommandLine", "medium") in found


def test_dotted_paths():
    assert ("Image", "info") in problems({})


@pytest.mark.integration
def test_audit_live_index(engine, rule, sysmon_event):
    engine.create("nw-it-audit", "dynamic_text")
    engine.bulk("nw-it-audit", [sysmon_event])
    findings = audit_index(engine, "nw-it-audit")
    assert any(f.field == "Image" and f.severity == "high" for f in findings)
    assert readiness_table([rule], sample_inventory(engine, "nw-it-audit")) == {
        "ready": [rule.title]
    }
