"""Third evaluation: routing, synonyms and citations. The plan is in PREREGISTRATION-3.md.

    python evals/experiment3.py tune      # on the 41 queries already seen, writes frozen-3.json
    python evals/experiment3.py pool      # blind pool of fresh queries, in data/ak/
    python evals/experiment3.py score     # once, needs evals/fresh-labels.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

from beacon import evaluate as ev
from beacon.backends.local import LocalBackend
from beacon.citations import article_refs
from beacon.cli import index_documents
from beacon.embeddings import get_embedder
from beacon.models import read_corpus, read_jsonl, write_jsonl
from beacon.retrieval import Retriever

HERE = Path(__file__).parent
REPORTS = HERE.parent / "reports"
CORPUS = "data/ak/corpus.jsonl"
EMBEDDER = "onnx:data/models/multilingual-e5-small"
FROZEN = HERE / "frozen-3.json"
FRESH = HERE / "fresh-queries.jsonl"
LABELS = HERE / "fresh-labels.jsonl"
LABELS_B = HERE / "fresh-labels-b.jsonl"
POOL = Path("data/ak/fresh-pool.jsonl")
DROPPED = {"f-en-14", "f-nl-05"}
RESULT = REPORTS / "ak-routing.json"
K = 10

LAW_NAMES = {
    "avg": ("AVG", "GDPR"),
    "aia": ("AI-verordening", "AI Act"),
    "awb": ("Awb", "Awb"),
    "grondwet": ("Grondwet", "Dutch Constitution"),
}


def build() -> tuple[Retriever, list]:
    documents = read_corpus(CORPUS)
    embedder = get_embedder(EMBEDDER, "data/cache")
    backend = LocalBackend()
    index_documents(backend, embedder, documents, title_prefix=True)
    return Retriever(backend, embedder), documents


def variants(base: Retriever, routing: str = "lang", power: float = 1.0) -> dict[str, Retriever]:
    return {
        "rrf": replace(base, routing="none"),
        "routed": replace(base, routing=routing, routing_power=power),
        "synonyms": replace(base, synonyms=True),
        "refs": replace(base, refs=True),
        "all": replace(base, routing=routing, routing_power=power, synonyms=True, refs=True),
    }


def rank(retriever: Retriever, k: int = K):
    return lambda query: [hit.chunk.doc_id for hit in retriever.search(query, "smart", k)]


def mean(run: ev.RunResult, ids=None, metric: str = "ndcg@10") -> float:
    values = run.per_query[metric]
    return float(np.mean([values[i] for i in (ids or values)]))


def tune() -> None:
    base, _ = build()
    queries = ev.load_queries(HERE / "hand-labels.jsonl")
    candidates = {"rrf": replace(base, routing="none"), "lang": replace(base, routing="lang")}
    for power in (1, 2, 4):
        candidates[f"coverage-{power}"] = replace(base, routing="coverage", routing_power=power)
    runs = {name: ev.evaluate_run(name, rank(r), queries) for name, r in candidates.items()}
    kinds = sorted({q.kind for q in queries})
    table = {
        name: {
            "all": mean(run),
            **{
                kind: mean(run, [q.id for q in queries if q.kind == kind])
                for kind in kinds
            },
        }
        for name, run in runs.items()
    }
    for name, row in table.items():
        print(name, {key: round(value, 3) for key, value in row.items()})
    best = max((n for n in table if n != "rrf"), key=lambda name: table[name]["all"])
    frozen = {
        "routing": "lang" if best == "lang" else "coverage",
        "power": 1 if best == "lang" else int(best.rpartition("-")[2]),
        "tuning": table,
    }
    FROZEN.write_text(json.dumps(frozen, indent=2) + "\n", encoding="utf-8")
    print("frozen:", best)


def fresh_queries() -> list[dict]:
    return [row for row in read_jsonl(FRESH) if row["id"] not in DROPPED]


def pool() -> None:
    """Depth-10 pool over every variant, shuffled per query so that order tells nothing."""
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    base, documents = build()
    by_id = {d.id: d for d in documents}
    rankers = {n: rank(r) for n, r in variants(base, frozen["routing"], frozen["power"]).items()}
    rankers["bm25"] = lambda q: [h.chunk.doc_id for h in base.search(q, "bm25", K)]
    rankers["dense"] = lambda q: [h.chunk.doc_id for h in base.search(q, "dense", K)]
    rows = []
    for query in fresh_queries():
        ids = ev.pool({name: run(query["query"]) for name, run in rankers.items()}, K)
        random.Random(query["id"]).shuffle(ids)
        rows.append(
            {
                "id": query["id"],
                "query": query["query"],
                "documents": [
                    {
                        "id": doc,
                        "title": by_id[doc].title,
                        "type": by_id[doc].doc_type,
                        "summary": by_id[doc].summary[:300],
                        "start": " ".join(by_id[doc].text.split())[:700],
                    }
                    for doc in ids
                ],
            }
        )
    write_jsonl(POOL, rows)
    print(len(rows), "queries,", sum(len(r["documents"]) for r in rows), "judgements in", POOL)


def statute_queries(documents) -> list[ev.Query]:
    """One query per wording for each article cited by a requirement page."""
    citing: dict[str, list[str]] = {}
    for document in documents:
        for ref in article_refs(document.refs):
            citing.setdefault(ref, []).append(document.id)
    queries = []
    for ref, pages in sorted(citing.items()):
        law, _, article = ref.partition(":")
        if law not in LAW_NAMES:
            continue
        dutch, english = LAW_NAMES[law]
        wordings = {
            "nl": f"artikel {article} {dutch}",
            "abbr": f"art. {article} {dutch}",
            "en": f"Article {article} {english}",
            "rev": f"{dutch} artikel {article}",
        }
        for name, text in wordings.items():
            digest = hashlib.sha256(ref.encode()).digest()[0]
            split = "dev" if digest % 2 == 0 else "test"
            queries.append(
                ev.Query(f"st-{ref}-{name}", text, {page: 2 for page in pages}, name, split)
            )
    return queries


def load_fresh(path: Path) -> list[ev.Query]:
    return [q for q in ev.load_queries(path) if q.id not in DROPPED]


def kappa(a: dict, b: dict) -> dict:
    """Linear weighted Cohen's kappa over the pairs both annotators judged."""
    pairs = [
        (a[query].get(doc, 0), b[query].get(doc, 0))
        for query in a
        for doc in sorted(set(a[query]) | set(b.get(query, {})))
    ]
    x, y = np.array(pairs).T
    observed = np.abs(x - y).mean()
    expected = np.mean([abs(i - j) for i in x for j in y])
    return {"pairs": len(pairs), "kappa": round(float(1 - observed / expected), 3)}


def compare(better: ev.RunResult, worse: ev.RunResult, ids: list[str]) -> dict:
    a, b = better.values("ndcg@10", ids), worse.values("ndcg@10", ids)
    differences = np.array(a) - np.array(b)
    low, high = ev.bootstrap_ci(differences)
    p = ev.permutation_test(a, b)
    return {
        "n": len(ids),
        "better": round(float(np.mean(a)), 3),
        "baseline": round(float(np.mean(b)), 3),
        "difference": round(float(differences.mean()), 3),
        "ci95": [round(float(low), 3), round(float(high), 3)],
        # Two-sided from the test, halved when the sign is the expected one.
        "p_one_sided": round(p / 2 if differences.mean() > 0 else 1 - p / 2, 4),
    }


def score() -> None:
    if RESULT.exists():
        sys.exit(f"{RESULT} exists: the fresh queries were already scored once.")
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    base, documents = build()
    runs_retrievers = variants(base, frozen["routing"], frozen["power"])
    queries = load_fresh(LABELS)
    ids = {
        kind: [q.id for q in queries if q.kind == kind] for kind in ("en", "other", "nl", "abbr")
    }
    foreign = ids["en"] + ids["other"]
    runs = {n: ev.evaluate_run(n, rank(r), queries) for n, r in runs_retrievers.items()}
    runs["bm25"] = ev.evaluate_run(
        "bm25", lambda q: [h.chunk.doc_id for h in base.search(q, "bm25", K)], queries
    )
    runs["dense"] = ev.evaluate_run(
        "dense", lambda q: [h.chunk.doc_id for h in base.search(q, "dense", K)], queries
    )
    statute = [q for q in statute_queries(documents) if q.split == "test"]
    statute_ids = [q.id for q in statute]
    statute_runs = {
        name: ev.evaluate_run(name, rank(runs_retrievers[name]), statute)
        for name in ("rrf", "refs")
    }
    tests = {
        "h1_router_foreign": compare(runs["routed"], runs["rrf"], foreign),
        "h2_router_dutch": compare(runs["routed"], runs["rrf"], ids["nl"]),
        "h3_synonyms_abbr": compare(runs["synonyms"], runs["rrf"], ids["abbr"]),
        "h4_refs_statute": compare(statute_runs["refs"], statute_runs["rrf"], statute_ids),
    }
    adjusted = ev.holm([tests[n]["p_one_sided"] for n in tests if not n.startswith("h2")])
    for name, value in zip(
        [n for n in tests if not n.startswith("h2")], adjusted, strict=True
    ):
        tests[name]["p_holm"] = round(value, 4)
    table = {
        name: {
            "all": round(mean(run, [q.id for q in queries]), 3),
            "recall@10": round(mean(run, [q.id for q in queries], "recall@10"), 3),
            **{kind: round(mean(run, group), 3) for kind, group in ids.items()},
        }
        for name, run in runs.items()
    }
    summary = {"frozen": frozen["routing"], "power": frozen["power"], "tests": tests, "table": table}
    summary["statute"] = {
        name: {
            kind: round(mean(run, [q.id for q in statute if q.kind == kind]), 3)
            for kind in ("nl", "abbr", "en", "rev")
        }
        for name, run in statute_runs.items()
    }
    summary["statute_queries"] = len(statute)
    if LABELS_B.exists():
        first = {q.id: q.relevant for q in queries}
        second_queries = load_fresh(LABELS_B)
        second = {q.id: q.relevant for q in second_queries}
        summary["agreement"] = kappa(first, second)
        rerun = {
            name: ev.evaluate_run(name, rank(runs_retrievers[name]), second_queries)
            for name in ("rrf", "routed", "synonyms")
        }
        summary["second_annotator"] = {
            "h1_router_foreign": compare(rerun["routed"], rerun["rrf"], foreign),
            "h2_router_dutch": compare(rerun["routed"], rerun["rrf"], ids["nl"]),
            "h3_synonyms_abbr": compare(rerun["synonyms"], rerun["rrf"], ids["abbr"]),
        }
    RESULT.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("tune", "pool", "score"))
    stage = parser.parse_args().stage
    {"tune": tune, "pool": pool, "score": score}[stage]()
