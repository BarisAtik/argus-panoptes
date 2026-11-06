"""Does Lucene agree with the in-process BM25? Dev queries only.

The holdout was scored on the in-process backend, whose stemmer and tokeniser only approximate
the Lucene analyzer. This indexes the same chunks in a Lucene engine with and without the
compound filter, and scores BM25 on the dev queries.

    python evals/lucene_check.py --url http://localhost:9201
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx
import numpy as np

from beacon import evaluate as ev
from beacon.backends.elastic import index_body
from beacon.chunking import chunk_document
from beacon.compounds import build_vocabulary, compound_vocabulary
from beacon.models import read_corpus

CORPUS = "data/ak/corpus.jsonl"
SETS = ("data/ak/queries-audit.jsonl", "data/ak/queries-requirements.jsonl")
OUT = Path(__file__).parent.parent / "reports" / "ak-lucene-check.md"
MAX_WORDS = 30_000


def create(url: str, name: str, words: list[str] | None, chunks) -> None:
    body = index_body(8, words)
    body["mappings"].pop("_source")
    del body["mappings"]["properties"]["embedding"]
    httpx.delete(f"{url}/{name}")
    httpx.put(f"{url}/{name}", json=body, timeout=60).raise_for_status()
    lines = []
    for chunk in chunks:
        lines.append(json.dumps({"index": {"_index": name, "_id": chunk.id}}))
        source = {k: v for k, v in chunk.source().items() if v != ""}
        lines.append(json.dumps(source, ensure_ascii=False))
    response = httpx.post(
        f"{url}/_bulk?refresh=true",
        content="\n".join(lines) + "\n",
        headers={"Content-Type": "application/x-ndjson"},
        timeout=120,
    )
    response.raise_for_status()
    if response.json()["errors"]:
        raise RuntimeError("bulk indexing failed")


def rank(url: str, name: str, query: str, k: int = 10) -> list[str]:
    body = {
        "size": 100,
        "_source": ["doc_id"],
        "query": {"bool": {"must": [{"match": {"text": query}}],
                           "filter": [{"term": {"doc_type": "maatregel"}}]}},
    }  # fmt: skip
    hits = httpx.post(f"{url}/{name}/_search", json=body, timeout=30).json()["hits"]["hits"]
    documents = dict.fromkeys(hit["_source"]["doc_id"] for hit in hits)
    return list(documents)[:k]


def terms(url: str, name: str, text: str) -> list[str]:
    body = {"analyzer": "dutch_compound", "text": text}
    return [t["token"] for t in httpx.post(f"{url}/{name}/_analyze", json=body).json()["tokens"]]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:9201")
    url = parser.parse_args().url
    documents = read_corpus(CORPUS)
    chunks = [c for d in documents for c in chunk_document(d)]
    words = list(build_vocabulary(d.text for d in documents))
    both = compound_vocabulary(d.text for d in documents)
    lexicon = sorted(both, key=lambda word: -both[word])[:MAX_WORDS]
    create(url, "ak-dutch", None, chunks)
    create(url, "ak-compound", words, chunks)
    create(url, "ak-lexicon", lexicon, chunks)
    queries = [q for path in SETS for q in ev.load_queries(path) if q.split == "dev"]
    runs = [
        ev.evaluate_run(name, lambda q, n=index: rank(url, n, q), queries)
        for name, index in (
            ("dutch", "ak-dutch"),
            ("compounds, corpus words", "ak-compound"),
            ("compounds, corpus and common words", "ak-lexicon"),
        )
    ]
    means = {
        run.name: {m: float(np.mean(list(run.per_query[m].values())))
                   for m in ("ndcg@10", "recall@10")}
        for run in runs
    }  # fmt: skip
    ids = [q.id for q in queries]
    p = ev.permutation_test(runs[2].values("ndcg@10", ids), runs[0].values("ndcg@10", ids))

    def shown(word: str) -> str:
        return " ".join(terms(url, "ak-lexicon", word))

    lines = [
        "# BM25 on Lucene, with and without compound splitting", "",
        f"{len(queries)} dev queries, measures only, default chunks. Word lists of {len(words)} "
        f"and {len(lexicon)} words. Exploratory. The engine is OpenSearch 3.9 on Lucene 10.5, "
        "used because Elasticsearch could not be downloaded. Settings come from `index_body`.",
        "",
        "| Analyzer | nDCG@10 | recall@10 |", "| --- | --- | --- |",
    ]  # fmt: skip
    for name, row in means.items():
        lines.append(f"| {name} | {row['ndcg@10']:.3f} | {row['recall@10']:.3f} |")
    lines += [
        "", f"Paired sign-flip test on nDCG@10, common-word list vs plain: p = {p:.3f}.", "",
        "Tokens for `algoritmeregister`: `" + shown("algoritmeregister") + "`.",
        "Tokens for `verantwoordelijkheid`: `" + shown("verantwoordelijkheid") + "`, "
        "which shows the cost: Lucene finds words inside words, so noise like `lijk` gets in.", "",
        "The in-process BM25 on the same queries scored 0.573 (`ak-dev-tuning.md`).",
    ]  # fmt: skip
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
