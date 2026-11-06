"""Run the planned experiments. See PREREGISTRATION.md.

    python evals/experiment.py regress --split dev --url http://localhost:9201
    python evals/experiment.py detect  --split dev --variant keyword_lower --url ...

`--split test` writes to reports/ and refuses to run twice.
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from collections import Counter
from importlib import metadata
from pathlib import Path

from nightwatch import config
from nightwatch.convert import Converted, convert
from nightwatch.engine import CHUNKED, VARIANTS, Engine, QueryFailed, chunk_long_values, read_jsonl
from nightwatch.evaluate import clustered_permutation, holm, mcnemar_one_sided, on_target, wilson
from nightwatch.readiness import build_inventory, check
from nightwatch.rules import Rule, load_rules
from nightwatch.sqlstore import SqlStore

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"
SEVERE = {"high", "critical"}
MILD = {"low", "medium"}


def guard(split: str, name: str) -> Path:
    path = REPORTS / f"{name}.json" if split == "test" else config.DATA_DIR / f"{name}-dev.json"
    if split == "test" and path.exists():
        sys.exit(f"{path} exists. The test split was scored once; write a new plan to go again.")
    return path


def provenance(engine: Engine) -> dict:
    version = engine.info()["version"]
    return {
        "sigma_commit": config.SIGMA_COMMIT,
        "datasets_commit": config.DATASETS_COMMIT,
        "engine": f"{version.get('distribution', 'elasticsearch')} {version['number']}",
        "lucene": version.get("lucene_version"),
        "pysigma": metadata.version("pysigma"),
        "lucene_backend": metadata.version("pysigma-backend-elasticsearch"),
    }


def load_all() -> tuple[list[Rule], dict[str, Converted]]:
    root = config.SIGMA_DIR
    rules, skipped = load_rules(
        root / "rules", root / "rules-threat-hunting", root / "rules-emerging-threats"
    )
    rules = [r for r in rules if r.sigma.logsource.product == "windows"]
    print(f"{len(rules)} Windows rules, {len(skipped)} skipped", flush=True)
    return rules, {r.id: convert(r.sigma) for r in rules}


def regress(args: argparse.Namespace) -> None:
    out = guard(args.split, "regression")
    engine = Engine(args.url)
    rules, converted = load_all()
    by_id = {r.id: r for r in rules}
    cases = json.loads(config.REGRESSION_CORPUS.with_suffix(".cases.json").read_text())
    cases = {
        rule_id: case
        for rule_id, case in cases.items()
        if case["split"] == args.split
        and rule_id in by_id
        and converted[rule_id].lucene
        and not converted[rule_id].unbound
    }
    events = [e for e in read_jsonl(config.REGRESSION_CORPUS) if e["case_id"] in cases]
    print(f"{len(cases)} cases, {len(events)} events", flush=True)

    fired: dict[str, dict[str, int]] = {}
    cross: dict[str, int] = {}
    failures: dict[str, dict[str, str]] = {}
    for variant in VARIANTS:
        index = f"nw-regress-{variant.replace('_', '-')}"
        engine.create(index, variant)
        stats = engine.bulk(index, map(chunk_long_values, events) if variant in CHUNKED else events)
        hits, failed, others = {}, {}, 0
        for rule_id in cases:
            query = converted[rule_id].lucene
            if variant == "tuned":
                query = converted[rule_id].lucene_tuned or query
            try:
                counts = engine.counts_by(index, query, "case_id")
            except QueryFailed as error:
                failed[rule_id] = str(error)
                continue
            hits[rule_id] = counts.get(rule_id, 0)
            others += sum(n for key, n in counts.items() if key != rule_id)
        fired[variant], failures[variant], cross[variant] = hits, failed, others
        print(variant, stats, sum(n > 0 for n in hits.values()), len(failed), flush=True)
        engine.client.delete(f"/{index}")

    store = SqlStore(events)
    hits, failed, others = {}, {}, 0
    for rule_id in cases:
        where = converted[rule_id].sql_where
        if where is None:
            failed[rule_id] = "no SQL conversion"
            continue
        try:
            counts = store.counts_by(where, "case_id")
        except Exception as error:  # noqa: BLE001 - a broken query is a result here
            failed[rule_id] = f"{type(error).__name__}: {error}"[:200]
            continue
        hits[rule_id] = counts.get(rule_id, 0)
        others += sum(n for key, n in counts.items() if key != rule_id)
    fired["sqlite"], failures["sqlite"], cross["sqlite"] = hits, failed, others

    n = len(cases)
    summary = {}
    for variant, hits in fired.items():
        fires = sum(hits.get(rule_id, 0) > 0 for rule_id in cases)
        exact = sum(hits.get(rule_id, -1) == cases[rule_id]["match_count"] for rule_id in cases)
        summary[variant] = {
            "fires": fires,
            "fire_rate": fires / n,
            "wilson": wilson(fires, n),
            "exact": exact,
            "failed_queries": len(failures[variant]),
            "hits_on_other_cases": cross[variant],
        }

    def compare(baseline: str, variant: str = "keyword_lower") -> dict:
        better = [
            r for r in cases if fired[variant].get(r, 0) > 0 and fired[baseline].get(r, 0) == 0
        ]
        worse = [
            r for r in cases if fired[variant].get(r, 0) == 0 and fired[baseline].get(r, 0) > 0
        ]
        return {
            "better": len(better),
            "worse": len(worse),
            "p": mcnemar_one_sided(len(better), len(worse)),
            "worse_cases": worse,
            "better_cases": better,
        }

    tests = {
        "A1": compare("keyword_raw"),
        "A2": compare("dynamic_text"),
        "A3": compare("keyword_lower_1024"),
        "A4": compare("keyword_lower", "keyword_lower_chunked"),
        "A5": compare("keyword_lower_chunked", "tuned"),
    }
    adjusted = holm({name: test["p"] for name, test in tests.items()})
    for name, test in tests.items():
        test["p_holm"] = adjusted[name]
    disagreements = {
        rule_id: {
            "title": by_id[rule_id].title,
            "keyword_lower": fired["keyword_lower"].get(rule_id),
            "sqlite": fired["sqlite"].get(rule_id),
            "expected": cases[rule_id]["match_count"],
            "lucene": converted[rule_id].lucene[:400],
        }
        for rule_id in cases
        if (fired["keyword_lower"].get(rule_id, 0) > 0) != (fired["sqlite"].get(rule_id, 0) > 0)
    }
    never = [r for r in cases if not any(fired[v].get(r, 0) for v in fired)]
    result = {
        "split": args.split,
        "cases": n,
        "provenance": provenance(engine),
        "summary": summary,
        "tests": tests,
        "disagreements": disagreements,
        "failures": {
            k: dict(Counter(v.split(":")[0] for v in f.values())) for k, f in failures.items()
        },
        "failed_rules": {k: dict(list(f.items())[:15]) for k, f in failures.items()},
        "never_fired": [{"id": r, "title": by_id[r].title} for r in never],
        "chosen": max(
            [v for v in VARIANTS],
            key=lambda v: (summary[v]["fires"], v == "keyword_lower"),
        ),
    }
    out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("cases", "summary", "chosen")}, indent=0))
    for name, test in tests.items():
        print(name, test["better"], test["worse"], test["p"], test["p_holm"])
    print("disagreements", len(disagreements), "never", len(never))


def detect(args: argparse.Namespace) -> None:
    out = guard(args.split, f"detection-{args.variant}")
    engine = Engine(args.url, timeout=300)
    root = config.SIGMA_DIR
    rules, skipped = load_rules(root / "rules" / "windows")
    datasets = json.loads(config.ATTACK_INDEX.read_text())
    chosen = {d["dataset_id"]: d for d in datasets if d["split"] == args.split}

    inventory = build_inventory(
        e for e in read_jsonl(config.ATTACK_CORPUS) if e["dataset_id"] in chosen
    )
    verdicts = {r.id: check(r.sigma, inventory) for r in rules}
    missing = Counter(name for v in verdicts.values() for name in v.missing)

    index = f"nw-attack-{args.split}-{args.variant.replace('_', '-')}"
    existing = engine.client.get(f"/{index}/_count")
    if existing.status_code != 200:
        engine.create(index, args.variant)
        stats = engine.bulk(
            index,
            (
                chunk_long_values(e) if args.variant in CHUNKED else e
                for e in read_jsonl(config.ATTACK_CORPUS)
                if e["dataset_id"] in chosen
            ),
        )
    else:
        stats = {"indexed": existing.json()["count"], "rejected": 0}
    print(stats, flush=True)

    usable, failed, pairs = [], {}, []
    for rule in rules:
        item = convert(rule.sigma)
        query = item.lucene_tuned if args.variant == "tuned" else item.lucene
        query = query or item.lucene
        if not query or item.unbound:
            continue
        usable.append(rule)
        try:
            counts = engine.counts_by(index, query, "dataset_id")
        except QueryFailed as error:
            failed[rule.id] = str(error)
            continue
        pairs += [
            {
                "rule": rule.id,
                "dataset": dataset_id,
                "hits": hits,
                "level": rule.level,
                "status": rule.status,
                "on_target": on_target(rule.techniques, chosen[dataset_id]["techniques"]),
                "predates": rule.created <= chosen[dataset_id]["created"],
            }
            for dataset_id, hits in counts.items()
        ]
    print(len(usable), len(failed), len(pairs), flush=True)
    by_dataset: dict[str, list[dict]] = {d: [] for d in chosen}
    for pair in pairs:
        by_dataset[pair["dataset"]].append(pair)

    any_alert = sum(bool(v) for v in by_dataset.values())
    recall_all = {d for d, v in by_dataset.items() if any(p["on_target"] for p in v)}
    recall_old = {
        d for d, v in by_dataset.items() if any(p["on_target"] and p["predates"] for p in v)
    }
    n = len(chosen)
    b1 = {
        "all_rules": len(recall_all),
        "predated_rules": len(recall_old),
        "n": n,
        "only_all": len(recall_all - recall_old),
        "only_predated": len(recall_old - recall_all),
        "p": mcnemar_one_sided(len(recall_all - recall_old), len(recall_old - recall_all)),
        "missed_by_all": sorted(
            f"{d}: {chosen[d]['title']}" for d in chosen if d not in recall_all
        ),
    }
    graded = [p for p in pairs if p["level"] in SEVERE | MILD]
    outcome = [int(p["on_target"]) for p in graded]
    group = [int(p["level"] in SEVERE) for p in graded]
    cluster = [p["rule"] for p in graded]
    difference, p_value = clustered_permutation(outcome, group, cluster)
    b2 = {
        "pairs": len(graded),
        "rules": len(set(cluster)),
        "share_severe": sum(o for o, g in zip(outcome, group, strict=True) if g)
        / max(1, sum(group)),
        "share_mild": sum(o for o, g in zip(outcome, group, strict=True) if not g)
        / max(1, len(group) - sum(group)),
        "difference": difference,
        "p": p_value,
    }
    adjusted = holm({"B1": b1["p"], "B2": b2["p"]})
    b1["p_holm"], b2["p_holm"] = adjusted["B1"], adjusted["B2"]

    spread = Counter(p["rule"] for p in pairs)
    titles = {r.id: r for r in rules}
    result = {
        "split": args.split,
        "variant": args.variant,
        "provenance": provenance(engine),
        "index": stats,
        "rules": {
            "parsed": len(rules),
            "skipped": len(skipped),
            "usable": len(usable),
            "failed_queries": len(failed),
            "ever_fired": len(spread),
        },
        "failures": dict(Counter(v.split(":")[0] for v in failed.values())),
        "readiness": dict(Counter(v.status for v in verdicts.values())),
        "most_missing_fields": missing.most_common(15),
        "datasets": n,
        "any_alert": any_alert,
        "any_alert_wilson": wilson(any_alert, n),
        "recall_wilson": wilson(len(recall_all), n),
        "firing_pairs": len(pairs),
        "on_target_share": sum(p["on_target"] for p in pairs) / max(1, len(pairs)),
        "B1": b1,
        "B2": b2,
        "noisiest": [
            {
                "title": titles[rule].title,
                "level": titles[rule].level,
                "datasets": count,
            }
            for rule, count in spread.most_common(15)
        ],
    }
    out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    (config.DATA_DIR / f"pairs-{args.split}-{args.variant}.json").write_text(json.dumps(pairs))
    print(json.dumps({k: v for k, v in result.items() if k != "B1"}, indent=0)[:2500])
    print({k: v for k, v in b1.items() if k != "missed_by_all"})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["regress", "detect"])
    parser.add_argument("--split", default="dev", choices=["dev", "test"])
    parser.add_argument("--variant", default="keyword_lower")
    parser.add_argument("--url", default=config.ES_URL)
    args = parser.parse_args()
    (regress if args.stage == "regress" else detect)(args)


if __name__ == "__main__":
    main()
