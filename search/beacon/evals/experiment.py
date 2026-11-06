"""Dev tuning and the one-shot holdout. The plan is in PREREGISTRATION.md.

    python evals/experiment.py dev
    python evals/experiment.py holdout
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import numpy as np

from beacon import evaluate as ev
from beacon.backends.local import LocalBackend
from beacon.cli import index_documents, ranker
from beacon.compounds import Decompounder, build_vocabulary
from beacon.embeddings import get_embedder
from beacon.models import Filters, read_corpus
from beacon.retrieval import Retriever
from beacon.text import tokens

HERE = Path(__file__).parent
REPORTS = HERE.parent / "reports"
CORPUS = "data/ak/corpus.jsonl"
SETS = ("data/ak/queries-audit.jsonl", "data/ak/queries-requirements.jsonl")
EMBEDDER = "onnx:data/models/multilingual-e5-small"
ONLY_MEASURES = Filters(doc_type="maatregel")
MIN_GAIN = 0.005


@dataclass(frozen=True)
class Config:
    max_words: int = 220
    overlap_words: int = 40
    title_prefix: bool = False
    compounds: bool = False
    rrf_k: int = 60


def build(config: Config, documents, embedder) -> Retriever:
    decompounder = None
    if config.compounds:
        decompounder = Decompounder(build_vocabulary(d.text for d in documents))
    backend = LocalBackend(decompounder=decompounder)
    index_documents(
        backend, embedder, documents,
        max_words=config.max_words, overlap_words=config.overlap_words,
        title_prefix=config.title_prefix,
    )  # fmt: skip
    return Retriever(backend, embedder, rrf_k=config.rrf_k)


def load(split: str) -> list[ev.Query]:
    return [q for path in SETS for q in ev.load_queries(path) if q.split == split]


def score(retriever: Retriever, mode: str, queries, name: str | None = None) -> ev.RunResult:
    return ev.evaluate_run(name or mode, ranker(retriever, mode, 10, ONLY_MEASURES), queries)


def mean(run: ev.RunResult, metric: str = "ndcg@10") -> float:
    return float(np.mean(list(run.per_query[metric].values())))


def overlap_check(documents, queries) -> dict:
    """Is a query's text simply copied in its answer? Share of query stems found in a page."""
    stems = {d.id: set(tokens(f"{d.title} {d.summary} {d.text}")) for d in documents}
    measures = [d.id for d in documents if d.doc_type == "maatregel"]
    relevant, other = [], []
    for query in queries:
        terms = set(tokens(query.text))
        if not terms:
            continue
        relevant.append(np.mean([len(terms & stems[d]) / len(terms) for d in query.relevant]))
        other.append(np.mean([len(terms & stems[d]) / len(terms) for d in measures]))
    return {"relevant_pages": float(np.mean(relevant)), "all_measures": float(np.mean(other))}


def dev() -> None:
    documents = read_corpus(CORPUS)
    embedder = get_embedder(EMBEDDER, "data/embeddings")
    queries = load("dev")
    trials = {"default": Config()}
    trials |= {
        "chunks-120": Config(max_words=120, overlap_words=20),
        "chunks-350": Config(max_words=350, overlap_words=50),
        "title-prefix": Config(title_prefix=True),
        "compounds": Config(compounds=True),
        "rrf-k-10": Config(rrf_k=10),
        "rrf-k-30": Config(rrf_k=30),
        "rrf-k-100": Config(rrf_k=100),
    }
    rows = {}
    for name, config in trials.items():
        started = time.time()
        retriever = build(config, documents, embedder)
        rows[name] = {
            mode: mean(score(retriever, mode, queries)) for mode in ("bm25", "dense", "rrf")
        }
        rows[name]["recall@10 rrf"] = mean(score(retriever, "rrf", queries), "recall@10")
        print(name, {k: round(v, 4) for k, v in rows[name].items()},
              f"{time.time() - started:.0f}s", flush=True)  # fmt: skip

    base = rows["default"]["rrf"]
    chosen = Config()
    # One change per group, the best one if it clears the bar. `rrf` is the score that decides.
    groups = [("chunks-120", "chunks-350"), ("title-prefix",), ("compounds",),
              ("rrf-k-10", "rrf-k-30", "rrf-k-100")]  # fmt: skip
    decisions = []
    for group in groups:
        best = max(group, key=lambda name: rows[name]["rrf"])
        gain = rows[best]["rrf"] - base
        keep = gain >= MIN_GAIN
        decisions.append({"best": best, "gain": gain, "kept": keep})
        if keep:
            changes = {k: v for k, v in asdict(trials[best]).items() if v != asdict(Config())[k]}
            chosen = replace(chosen, **changes)
    final = build(chosen, documents, embedder)
    frozen = {"config": asdict(chosen), "decisions": decisions,
              "dev_rrf_ndcg10_combined": mean(score(final, "rrf", queries))}  # fmt: skip
    (HERE / "frozen.json").write_text(json.dumps(frozen, indent=2), encoding="utf-8")

    lines = ["# Dev tuning on the Algoritmekader", "",
             f"{len(queries)} dev queries, measures only, embedder `{embedder.name}`, in-process "
             "backend. Every value is mean nDCG@10 unless the column says otherwise.", "",
             "| Trial | bm25 | dense | rrf | recall@10 rrf |",
             "| --- | --- | --- | --- | --- |"]  # fmt: skip
    for name, row in rows.items():
        lines.append(f"| {name} | {row['bm25']:.3f} | {row['dense']:.3f} | {row['rrf']:.3f} "
                     f"| {row['recall@10 rrf']:.3f} |")  # fmt: skip
    lines += ["", "## Decisions", ""]
    for decision in decisions:
        verdict = "kept" if decision["kept"] else "dropped"
        lines.append(f"- `{decision['best']}`: {decision['gain']:+.3f} on rrf, {verdict}")
    overlap = overlap_check(documents, queries)
    lines += ["", f"Frozen: `{json.dumps(asdict(chosen))}`, combined dev nDCG@10 "
              f"{frozen['dev_rrf_ndcg10_combined']:.3f}.", "",
              "Copying check: a relevant page holds "
              f"{overlap['relevant_pages']:.0%} of a query's stems, against "
              f"{overlap['all_measures']:.0%} for the average measure."]  # fmt: skip
    (REPORTS / "ak-dev-tuning.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def holdout() -> None:
    out = REPORTS / "ak-holdout.md"
    if out.exists():
        sys.exit("the holdout was already scored, and is scored once")
    frozen = Config(**json.loads((HERE / "frozen.json").read_text())["config"])
    documents = read_corpus(CORPUS)
    embedder = get_embedder(EMBEDDER, "data/embeddings")
    queries = load("test")
    default = build(Config(), documents, embedder)
    tuned = build(frozen, documents, embedder)
    bm25 = score(default, "bm25", queries)
    dense = score(default, "dense", queries)
    rrf = score(default, "rrf", queries)
    final = score(tuned, "rrf", queries, "frozen")
    summary = ev.summarise([bm25, dense, rrf, final], queries)
    pairs = [(rrf, bm25), (rrf, dense), (final, rrf)]
    ids = [q.id for q in queries]
    raw = [
        ev.permutation_test(a.values("ndcg@10", ids), b.values("ndcg@10", ids)) for a, b in pairs
    ]
    summary["comparisons"] = []
    for (a, b), p, p_holm in zip(pairs, raw, ev.holm(raw), strict=True):
        difference = np.array(a.values("ndcg@10", ids)) - np.array(b.values("ndcg@10", ids))
        low, high = ev.bootstrap_ci(difference.tolist())
        summary["comparisons"].append(
            {"run": a.name, "baseline": b.name, "metric": "ndcg@10",
             "difference": float(difference.mean()), "ci95": [low, high],
             "wins": int((difference > 0).sum()), "losses": int((difference < 0).sum()),
             "ties": int((difference == 0).sum()), "p": p, "p_holm": p_holm}
        )  # fmt: skip
    notes = [
        f"Scored once on {len(queries)} test queries, measures only.",
        f"Embedder {embedder.name}, in-process backend. Frozen config: {asdict(frozen)}.",
        "Labels come from the Algoritmekader project, and are probably incomplete.",
    ]
    markdown = ev.to_markdown(summary, "Holdout on the Algoritmekader", notes)
    out.write_text(markdown, encoding="utf-8")
    ev.save(summary, out.with_suffix(".json"))
    print(markdown)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=["dev", "holdout"])
    {"dev": dev, "holdout": holdout}[parser.parse_args().step]()
