"""Real engine behaviour, with invented events. Run with NIGHTWATCH_IT=1."""

import pytest

from nightwatch.convert import convert
from nightwatch.engine import CHUNK_CHARS, QueryFailed, chunk_long_values
from nightwatch.rules import parse_rule

pytestmark = pytest.mark.integration


def load(engine, variant, events):
    index = f"nw-it-{variant.replace('_', '-')}"
    engine.create(index, variant)
    assert engine.bulk(index, events)["rejected"] == 0
    return index


def test_mapping_decides_whether_a_rule_fires(engine, rule, sysmon_event):
    query = convert(rule.sigma).lucene
    fires = {
        variant: engine.count(load(engine, variant, [sysmon_event]), query)
        for variant in ("dynamic_text", "keyword_raw", "keyword_lower")
    }
    assert fires == {"dynamic_text": 0, "keyword_raw": 0, "keyword_lower": 1}


def test_ignore_above_hides_a_long_value_and_chunking_finds_it(engine):
    event = {"ScriptBlockText": "x" * (CHUNK_CHARS * 2) + " mimikatz " + "y" * 100}
    query = "ScriptBlockText:*mimikatz*"
    assert engine.count(load(engine, "keyword_lower", [event]), query) == 0
    index = load(engine, "keyword_lower_chunked", [chunk_long_values(event)])
    assert engine.count(index, query) == 1


def test_bad_query_raises_instead_of_returning_zero(engine, sysmon_event):
    index = load(engine, "keyword_lower", [sysmon_event])
    with pytest.raises(QueryFailed):
        engine.count(index, "Image:(")


def test_cidr_filter_only_works_when_expanded(engine):
    text = """
title: T
id: 44444444-4444-4444-8444-444444444444
logsource: {product: windows, service: security}
detection:
  selection: {EventID: 4624}
  filter: {IpAddress|cidr: '10.0.0.0/8'}
  condition: selection and not filter
"""
    converted = convert(parse_rule(text).sigma)
    event = {"Channel": "Security", "EventID": "4624", "IpAddress": "10.1.2.3"}
    index = load(engine, "keyword_lower", [event])
    assert engine.count(index, converted.lucene) == 1  # the filter did nothing
    assert engine.count(index, converted.lucene_tuned) == 0
