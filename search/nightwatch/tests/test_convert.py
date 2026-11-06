import re

import pytest

from nightwatch.convert import adapt_values, convert, lucene_regex
from nightwatch.rules import parse_rule

BODY = """
title: T
id: 22222222-2222-4222-8222-222222222222
status: test
level: low
logsource:
  category: process_creation
  product: windows
detection:
{detection}
"""


def rule(detection):
    return parse_rule(BODY.format(detection=detection)).sigma


def test_rule_metadata(rule):
    assert rule.status == "stable"
    assert rule.level == "high"
    assert rule.created == "2020-01-02"
    assert rule.techniques == ["T1059.001"]


def test_convert_applies_logsource_once(rule):
    converted = convert(rule.sigma)
    assert converted.lucene.count("EventID:1") == 1
    assert converted.sql_where.count("EventID=1") == 1


def test_convert_leaves_rule_untouched(rule):
    first = convert(rule.sigma)
    assert convert(rule.sigma).lucene == first.lucene


def test_keyword_rule_is_flagged():
    converted = convert(rule("  keywords:\n    - foo\n  condition: keywords"))
    assert converted.unbound


@pytest.mark.parametrize(
    "pattern,expected",
    [
        (r"abc", ".*abc.*"),
        (r"^abc$", "abc"),
        (r"^abc\$", r"abc\$.*"),
        (r"(?i)Ab(?:c|d)", ".*ab(c|d).*"),
        (r"\W\S", r".*\W\S.*"),  # escapes keep their case
        (r'a"b', r".*a\"b.*"),
        (r"a(?=b)", None),
    ],
)
def test_lucene_regex(pattern, expected):
    assert lucene_regex(pattern) == expected


def test_rewritten_regex_is_valid_python():
    assert re.compile(lucene_regex(r"(?i)foo[0-9]{2,4}\.exe$"))


def test_cidr_expanded_only_in_tuned():
    converted = convert(
        rule(
            "  selection:\n    EventID: 1\n  filter:\n    IpAddress|cidr: '10.0.0.0/8'\n"
            "  condition: selection and not filter"
        )
    )
    assert r"10.0.0.0\/8" in converted.lucene
    assert "10.*" in converted.lucene_tuned


def test_adapt_values_changes_regex():
    sigma = rule("  selection:\n    CommandLine|re: 'a.c'\n  condition: selection")
    adapt_values(sigma.detection.detections["selection"])
    assert sigma.detection.detections["selection"].detection_items[0].value[0].regexp
