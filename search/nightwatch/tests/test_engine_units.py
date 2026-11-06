from nightwatch.convert import convert
from nightwatch.engine import (
    CHUNK_CHARS,
    CHUNK_OVERLAP,
    IGNORE_ABOVE_SAFE,
    VARIANTS,
    chunk_long_values,
)
from nightwatch.sqlstore import SqlStore


def test_short_values_stay_scalar():
    assert chunk_long_values({"a": "x"}) == {"a": "x"}


def test_every_short_pattern_survives_chunking():
    value = "".join(f"{i:06d}" for i in range(6000))
    pieces = chunk_long_values({"a": value})["a"]
    assert all(len(p) <= CHUNK_CHARS <= IGNORE_ABOVE_SAFE for p in pieces)
    for start in range(0, len(value) - CHUNK_OVERLAP, 977):
        needle = value[start : start + CHUNK_OVERLAP]
        assert any(needle in piece for piece in pieces)


def test_variants_are_all_defined():
    assert {"dynamic_text", "keyword_lower", "tuned"} <= set(VARIANTS)


def test_sql_store_is_case_insensitive_like_sigma(rule, sysmon_event):
    store = SqlStore([sysmon_event | {"case_id": "a"}, {"Channel": "x", "case_id": "b"}])
    where = convert(rule.sigma).sql_where
    assert store.count(where) == 1
    assert store.counts_by(where, "case_id") == {"a": 1}
    assert store.rows(where)[0]["case_id"] == "a"


def test_sql_store_merges_columns_that_differ_in_case():
    store = SqlStore([{"ProcessId": "1"}, {"processId": "2"}])
    assert len(store.columns) == 1
    assert store.count("ProcessId IS NOT NULL") == 2
