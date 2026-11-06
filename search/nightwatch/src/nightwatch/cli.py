"""Command line. See README.md."""

from __future__ import annotations

import argparse
import itertools
import json
import warnings
from pathlib import Path

from . import config
from .audit import audit_index, readiness_table, sample_inventory
from .engine import VARIANTS, Engine, chunk_long_values, read_jsonl
from .readiness import build_inventory
from .rules import load_rules, parse_rule


def _engine(args: argparse.Namespace) -> Engine:
    return Engine(args.url, config.ES_USER if config.ES_PASSWORD else None, config.ES_PASSWORD)


def cmd_fetch(args: argparse.Namespace) -> None:
    from . import sources

    sources.fetch_sigma()
    print(f"regression cases: {len(sources.write_regression_corpus())}")
    if not args.rules_only:
        print(f"attack datasets: {len(sources.write_attack_corpus())}")


def cmd_index(args: argparse.Namespace) -> None:
    engine = _engine(args)
    engine.create(args.index, args.variant)
    events = read_jsonl(args.corpus)
    if args.variant in ("keyword_lower_chunked", "tuned"):
        events = map(chunk_long_values, events)
    print(engine.bulk(args.index, events))


def cmd_convert(args: argparse.Namespace) -> None:
    from sigma.backends.elasticsearch import EqlBackend, ESQLBackend, LuceneBackend
    from sigma.collection import SigmaCollection

    from .convert import convert, pipeline

    rule = parse_rule(Path(args.rule).read_text(encoding="utf-8"))
    if rule is None:
        raise SystemExit("not a usable Sigma rule")
    if args.to == "tuned":
        print(convert(rule.sigma).lucene_tuned)
        return
    backend = {"lucene": LuceneBackend, "esql": ESQLBackend, "eql": EqlBackend}[args.to]
    print(backend(pipeline()).convert(SigmaCollection([rule.sigma]))[0])


def _rules(args: argparse.Namespace):
    rules, _ = load_rules(Path(args.rules))
    return rules


def cmd_readiness(args: argparse.Namespace) -> None:
    inventory = build_inventory(read_jsonl(args.corpus))
    table = readiness_table(_rules(args), inventory)
    print(json.dumps({status: len(titles) for status, titles in table.items()}, indent=1))


def cmd_audit(args: argparse.Namespace) -> None:
    engine = _engine(args)
    for finding in audit_index(engine, args.index):
        print(f"[{finding.severity}] {finding.field}: {finding.problem}")
    table = readiness_table(_rules(args), sample_inventory(engine, args.index))
    print(json.dumps({status: len(titles) for status, titles in table.items()}, indent=1))


def cmd_mcp(args: argparse.Namespace) -> None:
    from .mcp_server import EngineStore, LocalStore, build_server
    from .sqlstore import SqlStore

    if args.index:
        engine = _engine(args)
        store = EngineStore(engine, args.index)
        inventory = sample_inventory(engine, args.index)
    else:
        events = list(itertools.islice(read_jsonl(args.corpus), args.max_events))
        store = LocalStore(SqlStore(events))
        inventory = build_inventory(events)
    build_server(_rules(args), store, inventory).run()


def main() -> None:
    warnings.filterwarnings("ignore")
    parser = argparse.ArgumentParser(prog="nightwatch", description=__doc__)
    parser.add_argument("--url", default=config.ES_URL)
    commands = parser.add_subparsers(dest="command", required=True)

    fetch = commands.add_parser("fetch", help="download rules and logs, pinned")
    fetch.add_argument("--rules-only", action="store_true")
    fetch.set_defaults(run=cmd_fetch)

    index = commands.add_parser("index", help="load a corpus into an engine")
    index.add_argument("--corpus", default=str(config.ATTACK_CORPUS))
    index.add_argument("--index", default="nightwatch-logs")
    index.add_argument("--variant", default="tuned", choices=list(VARIANTS))
    index.set_defaults(run=cmd_index)

    convert_rule = commands.add_parser("convert", help="print one rule as an engine query")
    convert_rule.add_argument("rule")
    convert_rule.add_argument("--to", default="tuned", choices=["tuned", "lucene", "esql", "eql"])
    convert_rule.set_defaults(run=cmd_convert)

    rules_default = str(config.SIGMA_DIR / "rules" / "windows")
    ready = commands.add_parser("readiness", help="which rules can fire on a JSONL corpus")
    ready.add_argument("--corpus", default=str(config.ATTACK_CORPUS))
    ready.add_argument("--rules", default=rules_default)
    ready.set_defaults(run=cmd_readiness)

    audit = commands.add_parser("audit", help="check a live index: mapping and readiness")
    audit.add_argument("--index", required=True)
    audit.add_argument("--rules", default=rules_default)
    audit.set_defaults(run=cmd_audit)

    mcp = commands.add_parser("mcp", help="serve read-only hunting tools over stdio")
    mcp.add_argument("--index", help="use an engine index instead of a local corpus")
    mcp.add_argument("--corpus", default=str(config.ATTACK_CORPUS))
    mcp.add_argument("--max-events", type=int, default=50000)
    mcp.add_argument("--rules", default=rules_default)
    mcp.set_defaults(run=cmd_mcp)

    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
