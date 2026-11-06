"""Search export, queries and cross-check. Engine tests run only with GAUNTLET_ES_URL set."""

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest
import yaml

from gauntlet.cli import main
from gauntlet.defenses import ablations
from gauntlet.report import BLOCK_REASONS, bulk_ndjson

ELASTIC = Path(__file__).resolve().parents[1] / "elastic"


def _module(name):
    spec = importlib.util.spec_from_file_location(name, ELASTIC / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ts = _module("trace_search")
rf = _module("run_with_finals")
STACKS = rf.DEFENSES.split(",") + list(ablations("layered").values())


@pytest.fixture(scope="module")
def trials():
    return rf.run("compromised", STACKS, 1)


@pytest.fixture(scope="module")
def docs(trials):
    lines = bulk_ndjson(trials).splitlines()
    return [json.loads(x) for x in lines[1::2]]


def _props():
    return ts.read_template()["template"]["mappings"]["properties"]


def test_bulk_format(trials):
    text = bulk_ndjson(trials, "x")
    assert text.endswith("\n")
    lines = [json.loads(x) for x in text.splitlines()]
    assert len(lines) == 2 * len(trials)
    assert all(a["index"]["_index"] == "x" for a in lines[::2])
    assert all("trace" not in d and "scenario" in d for d in lines[1::2])


def test_ids_unique(trials):
    ids = [json.loads(x)["index"]["_id"] for x in bulk_ndjson(trials).splitlines()[::2]]
    assert len(ids) == len(set(ids))


def test_mapping_covers_every_field(docs):
    props = _props()
    assert not {k for d in docs for k in d} - props.keys()
    inner = props["events"]["properties"]
    assert not {k for d in docs for e in d["events"] for k in e} - inner.keys()
    assert any(d["events"] for d in docs)
    assert ts.read_template()["template"]["mappings"]["dynamic"] == "strict"


def test_events_keep_tool_and_defense_together(docs):
    blocks = [e for d in docs for e in d["events"] if not e["executed"]]
    assert blocks and all(e["defense"] not in (None, "other") for e in blocks)


def test_block_reason_tables_agree(trials):
    assert set(BLOCK_REASONS.values()) == set(ts.REASON_DEFENSE.values())
    seen = {e["blocked_by"] for r in trials for e in r["trace"] if e["blocked_by"]}
    assert seen <= ts.REASON_DEFENSE.keys()


def _fields(node):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "terms" and "field" in v:
                yield v
            yield from _fields(v)
    elif isinstance(node, list):
        for v in node:
            yield from _fields(v)


def test_query_files_parse_and_are_safe():
    props, runtime = _props(), ts.read_template()["template"]["mappings"]["runtime"]
    props = {**props, **{f"events.{k}": v for k, v in props["events"]["properties"].items()}}
    queries = ts.read_queries()
    assert len(queries) >= 8 and len({q["name"] for q in queries.values()}) == len(queries)
    for qid, q in queries.items():
        assert q["name"] and q["question"] and q["columns"]
        assert q["body"]["track_total_hits"] is True, qid
        assert qid[:2] in ts.CHECK_KEYS
        for terms in _fields(q["body"]):
            assert terms["size"] >= 50, qid
            field = terms["field"]
            kind = runtime[field]["type"] if field in runtime else props[field]["type"]
            assert kind == "keyword", (qid, field)
            assert "ignore_above" not in props.get(field, {})


def test_runtime_becomes_derived_on_opensearch():
    t = ts.read_template()
    assert "runtime" in ts.for_engine(t, False)["template"]["mappings"]
    m = ts.for_engine(t, True)["template"]["mappings"]
    assert "derived" in m and "runtime" not in m


def _res(agg, total=10, relation="eq"):
    return {"hits": {"total": {"value": total, "relation": relation}}, "aggregations": {"d": agg}}


def test_check_accepts_a_clean_answer():
    ts.check_response(_res({"sum_other_doc_count": 0, "doc_count_error_upper_bound": 0,
                            "buckets": [{"key": "a", "doc_count": 7}, {"key": "b", "doc_count": 3}]}))


@pytest.mark.parametrize("res", [
    _res({"sum_other_doc_count": 4, "buckets": [{"key": "a", "doc_count": 6}]}),  # default size
    _res({"sum_other_doc_count": 0, "buckets": [{"key": "a", "doc_count": 25}]}),  # analyzed text
    _res({"sum_other_doc_count": 0, "buckets": [{"key": "a", "doc_count": 4}]}),  # dropped by ignore_above
    _res({"sum_other_doc_count": 0, "doc_count_error_upper_bound": 2, "buckets": [{"key": "a", "doc_count": 10}]}),
    _res({"buckets": [{"key": "a", "doc_count": 10000}]}, total=10000, relation="gte"),
    {"hits": {}, "aggregations": {}},
])
def test_check_catches_quiet_errors(res):
    with pytest.raises(ts.Failure):
        ts.check_response(res)


def test_check_allows_declared_multi_valued_field():
    res = _res({"sum_other_doc_count": 0, "buckets": [{"key": "a", "doc_count": 7}, {"key": "b", "doc_count": 7}]})
    ts.check_response(res, ["d"])


def test_flatten_goes_through_filters_and_nested():
    aggs = {"defense": {"buckets": [{"key": "dlp", "doc_count": 9, "ok": {"doc_count": 2},
                                     "events": {"doc_count": 20, "tool": {"buckets": [
                                         {"key": "x", "doc_count": 5, "blocks": {"doc_count": 1}},
                                         {"key": "y", "doc_count": 15, "blocks": {"doc_count": 0}}]}}}]}}
    rows = ts.flatten(aggs)
    assert len(rows) == 2
    assert rows[0] == {"defense": "dlp", "defense_n": 9, "ok": 2, "events": 20, "tool": "x", "tool_n": 5, "blocks": 1}


def test_compare_needs_every_number_to_match(trials):
    qid = "01_attack_success_by_defense"
    rows = [{"defense": k[0], **v} for k, v in ts.expected(qid, trials).items()]
    assert ts.compare(qid, rows, trials) > 0
    rows[0]["defense_n"] += 1
    with pytest.raises(ts.Failure):
        ts.compare(qid, rows, trials)


def test_rates_match_gauntlet_summary(trials):
    from gauntlet.report import summarize

    summary = summarize(trials)
    for (d,), cell in ts.expected("01", trials).items():
        assert cell["succeeded"] / cell["defense_n"] == pytest.approx(summary[d]["asr"])


def test_finals_wrapper_changes_nothing_else(tmp_path, trials):
    out = tmp_path / "plain.jsonl"
    assert main(["run", "--agent", "compromised", "--defenses", ",".join(STACKS), "--out", str(out)]) == 0
    plain = [json.loads(x) for x in out.read_text().splitlines()]
    stripped = [{k: v for k, v in json.loads(json.dumps(r)).items() if k not in ("final_answer", "run_at")} for r in trials]
    assert plain == stripped
    assert any(r["final_answer"] for r in trials)


def test_engine_refuses_other_hosts():
    with pytest.raises(SystemExit):
        ts.Engine("http://search.example.test:9200")


def test_compose_is_loopback_with_security_on():
    compose = yaml.safe_load((ELASTIC / "docker-compose.yml").read_text())
    es = compose["services"]["elasticsearch"]
    assert es["environment"]["xpack.security.enabled"] == "true"
    assert all(p.startswith("127.0.0.1:") for s in compose["services"].values() for p in s.get("ports", []))
    assert ":-9.5.6}" in es["image"]
    assert "ELASTIC_PASSWORD=change-me" in (ELASTIC / ".env.example").read_text()


def test_dashboard_is_marked_and_refers_to_real_fields():
    objs = [json.loads(x) for x in (ELASTIC / "dashboard.ndjson").read_text().splitlines()]
    summary, objs = objs[-1], objs[:-1]
    assert summary["exportedCount"] == len(objs)
    ids = {o["id"] for o in objs}
    assert all(r["id"] in ids for o in objs for r in o["references"])
    fields = _props().keys() | ts.read_template()["template"]["mappings"]["runtime"].keys()
    for o in objs:
        assert "never imported" in json.dumps(o["attributes"])
        if o["type"] == "visualization":
            for agg in json.loads(o["attributes"]["visState"])["aggs"]:
                assert agg["params"].get("field", "scenario") in fields
    panels = json.loads(next(o for o in objs if o["type"] == "dashboard")["attributes"]["panelsJSON"])
    assert len(panels) == 4


needs_engine = pytest.mark.skipif(not os.environ.get("GAUNTLET_ES_URL"), reason="GAUNTLET_ES_URL not set")


@pytest.fixture(scope="module")
def loaded(tmp_path_factory):
    rows = rf.run("compromised", STACKS, 3)
    bulk = tmp_path_factory.mktemp("es") / "bulk.ndjson"
    bulk.write_text(bulk_ndjson(rows))
    es = ts.engine_from_env()
    assert ts.load(es, bulk) == len(rows)
    return es, bulk, rows


@needs_engine
def test_every_query_agrees_with_the_jsonl(loaded):
    es, _, rows = loaded
    for qid, q in ts.read_queries().items():
        engine_rows, _ = ts.run_query(es, q)
        assert ts.compare(qid, engine_rows, rows) > 0, qid


@needs_engine
def test_search_time_field_works(loaded):
    es, _, rows = loaded
    q = ts.read_queries()["12_attack_success_by_family"]
    engine_rows, _ = ts.run_query(es, q)
    assert {r["family"] for r in engine_rows} == {r["scenario"].split("-")[0] for r in rows if not r["control"]}


@needs_engine
def test_deliberate_faults_are_all_caught(loaded):
    es, bulk, rows = loaded
    assert len(ts.fault_checks(es, bulk, ts.read_queries(), rows)) == 7


@needs_engine
def test_load_replaces_rather_than_adds(loaded):
    es, bulk, rows = loaded
    assert ts.load(es, bulk) == len(rows)
