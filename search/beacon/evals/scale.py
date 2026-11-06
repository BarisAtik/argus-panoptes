"""What changes when the corpus is 100 times bigger? Exploratory: every query here has been seen.

Adds the Logius standards (Dutch government IT, git documentation, read through `ingest-dir`) to
the Algoritmekader as distractors, then measures indexing cost, ANN recall, quantisation loss,
rule false positives and retrieval quality on the labelled queries.

`hnswlib` with Elasticsearch's default graph settings (M=16, ef_construction=100) stands in for
Lucene's HNSW, because no engine with HNSW can be installed here. It is the same algorithm family,
not the same code. Elasticsearch's own numbers must be measured there.

    git clone --depth 1 https://github.com/Logius-standaarden/publicatie <folder>
    python evals/scale.py <folder>
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import hnswlib
import numpy as np

from beacon import evaluate as ev
from beacon.backends.local import LocalBackend
from beacon.chunking import chunk_document
from beacon.embeddings import get_embedder
from beacon.injection import scan
from beacon.models import Hit, read_corpus
from beacon.retrieval import Retriever
from beacon.sources.files import AclRules, load_directory, report_markdown

HERE = Path(__file__).parent
REPORT = HERE.parent / "reports" / "scale.json"
EMBEDDER = "onnx:data/models/multilingual-e5-small"
K = 100
EF = (100, 200, 400)


class HnswBackend(LocalBackend):
    """LocalBackend with vector search replaced by a graph."""

    ef = 400
    graph = None

    def build(self) -> float:
        started = time.perf_counter()
        graph = hnswlib.Index(space="cosine", dim=self.vectors.shape[1])
        graph.init_index(len(self.vectors), ef_construction=100, M=16, random_seed=13)
        graph.add_items(self.vectors, num_threads=2)
        self.graph = graph
        return time.perf_counter() - started

    def dense(self, vector, k, filters=None):
        self.graph.set_ef(max(self.ef, k))
        labels, distances = self.graph.knn_query(vector, k=k)
        return [
            Hit(self.chunks[int(i)], 1 - float(d))
            for i, d in zip(labels[0], distances[0], strict=True)
            if filters is None or filters.matches(self.chunks[int(i)])
        ]


def int8(vectors: np.ndarray) -> tuple[np.ndarray, float, float]:
    """Scalar quantisation over the central 99.9% of values, close to what int8_hnsw does."""
    low, high = np.quantile(vectors, [0.0005, 0.9995])
    scale = 127 / (high - low)
    return np.clip(np.round((vectors - low) * scale), 0, 127).astype(np.int8), low, scale


def overlap(found: np.ndarray, truth: np.ndarray, k: int) -> float:
    return float(np.mean([len(set(a[:k]) & set(b[:k])) / k for a, b in zip(found, truth)]))


def main(folder: str) -> None:
    summary: dict = {}
    started = time.perf_counter()
    extra, report = load_directory(folder, AclRules(default=("public",)))
    summary["read_seconds"] = round(time.perf_counter() - started, 1)
    Path("data/scale-ingest-report.md").write_text(report_markdown(report), encoding="utf-8")
    summary["files_seen"] = report.files_seen
    summary["failed"] = len(report.failed)
    summary["redirects"] = report.redirects
    summary["duplicates"] = len(report.duplicates)
    summary["likely_scanned"] = len(report.likely_scanned)
    summary["partly_scanned"] = len(report.partly_scanned)

    ak = read_corpus("data/ak/corpus.jsonl")
    ak_chunks = [c for d in ak for c in chunk_document(d, title_prefix=True)]
    extra_chunks = [c for d in extra for c in chunk_document(d, title_prefix=True)]
    summary["documents"] = {"ak": len(ak), "logius": len(extra)}
    summary["chunks"] = {"ak": len(ak_chunks), "logius": len(extra_chunks)}

    flagged = [c for c in extra_chunks if scan(c.text)]
    rules: dict[str, int] = {}
    for chunk in flagged:
        for rule in scan(chunk.text):
            rules[rule] = rules.get(rule, 0) + 1
    summary["rule_false_positives"] = {
        "chunks": len(flagged), "of": len(extra_chunks), "by_rule": rules,
        "documents": report.injection_suspected.__len__(),
    }  # fmt: skip

    embedder = get_embedder(EMBEDDER, "data/cache")
    embed_started = time.perf_counter()
    batches = [
        embedder.embed_passages([c.text for c in extra_chunks[i : i + 64]])
        for i in range(0, len(extra_chunks), 64)
    ]
    summary["embed_seconds_logius"] = round(time.perf_counter() - embed_started, 1)
    small_vectors = embedder.embed_passages([c.text for c in ak_chunks])
    vectors = np.vstack([small_vectors, *batches]).astype(np.float32)
    chunks = ak_chunks + extra_chunks

    backend = HnswBackend()
    backend.add(chunks, vectors)
    summary["graph_build_seconds"] = round(backend.build(), 1)
    path = Path("data/scale.hnsw")
    backend.graph.save_index(str(path))
    summary["graph_mb"] = round(path.stat().st_size / 2**20, 1)
    summary["float_vectors_mb"] = round(vectors.nbytes / 2**20, 1)
    path.unlink()

    fresh = ev.load_queries(HERE / "fresh-labels.jsonl")
    seen = ev.load_queries(HERE / "hand-labels.jsonl")
    queries = fresh + seen
    embedded = np.vstack([embedder.embed_query(q.text) for q in queries]).astype(np.float32)

    timing_started = time.perf_counter()
    exact = np.argsort(-(vectors @ embedded.T).T, axis=1)[:, :K]
    summary["exact_ms_per_query"] = round(
        1000 * (time.perf_counter() - timing_started) / len(queries), 2
    )
    ann = {}
    for ef in EF:
        backend.graph.set_ef(ef)
        timing_started = time.perf_counter()
        found = np.vstack([backend.graph.knn_query(v, k=K)[0] for v in embedded])
        ms = 1000 * (time.perf_counter() - timing_started) / len(queries)
        ann[str(ef)] = {
            "recall@10": round(overlap(found, exact, 10), 4),
            "recall@100": round(overlap(found, exact, K), 4),
            "ms_per_query": round(ms, 2),
        }
    summary["hnsw_vs_exact"] = ann

    quantised, low, scale = int8(vectors)
    query_codes = np.round((embedded - low) * scale).astype(np.float32)
    scored = (query_codes @ quantised.astype(np.float32).T)
    close = np.argsort(-scored, axis=1)[:, :K]
    summary["int8_vs_float"] = {
        "recall@10": round(overlap(close, exact, 10), 4),
        "recall@100": round(overlap(close, exact, K), 4),
    }

    small = LocalBackend()
    small.add(ak_chunks, small_vectors)
    exact_big = LocalBackend()
    exact_big.add(chunks, vectors)

    def score(active, name, mode, data):
        retriever = Retriever(active, embedder, routing="lang", synonyms=True, refs=True)
        run = ev.evaluate_run(
            name, lambda q: [h.chunk.doc_id for h in retriever.search(q, mode, 10)], data
        )
        return round(float(np.mean(list(run.per_query["ndcg@10"].values()))), 3)

    table = {}
    actives = (("ak only", small), ("with distractors", exact_big), ("hnsw ef=400", backend))
    for name, active in actives:
        table[name] = {
            mode: score(active, f"{name}-{mode}", mode, fresh)
            for mode in ("bm25", "dense", "rrf", "smart")
        }
    summary["ndcg10_fresh"] = table
    summary["rule_false_positives"]["share"] = round(len(flagged) / len(extra_chunks), 4)
    Path(REPORT).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main(sys.argv[1])
