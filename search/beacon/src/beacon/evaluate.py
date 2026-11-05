"""Retrieval evaluation with uncertainty, not just a leaderboard.

Queries are the unit of analysis. Two configurations run on the same queries, so
comparisons are paired: a sign-flip permutation test on per-query differences, with a
Holm correction when several comparisons are made, and bootstrap confidence intervals.
"""

from __future__ import annotations

import json
import math
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .models import Document, read_jsonl
from .text import sentences


@dataclass
class Query:
    id: str
    text: str
    relevant: dict[str, int]  # document id -> grade; 2 = answers it, 1 = related
    kind: str = "general"


def load_queries(path: str | Path) -> list[Query]:
    queries = [
        Query(row["id"], row["query"], {k: int(v) for k, v in row["relevant"].items()},
              row.get("kind", "general"))
        for row in read_jsonl(path)
    ]
    ids = [q.id for q in queries]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate query ids in {path}")
    return queries


def check_labels(queries: Sequence[Query], document_ids: set[str]) -> list[str]:
    """Labels that point at nothing silently lower recall, so they are an error."""
    return [
        f"{query.id}: {doc_id}"
        for query in queries
        for doc_id in query.relevant
        if doc_id not in document_ids
    ]


def recall_at(ranked: Sequence[str], relevant: dict[str, int], k: int) -> float:
    positive = {d for d, grade in relevant.items() if grade > 0}
    if not positive:
        return 0.0
    return len(positive & set(ranked[:k])) / len(positive)


def ndcg_at(ranked: Sequence[str], relevant: dict[str, int], k: int) -> float:
    def dcg(grades: Sequence[int]) -> float:
        return sum((2**g - 1) / math.log2(rank + 2) for rank, g in enumerate(grades))

    ideal = dcg(sorted(relevant.values(), reverse=True)[:k])
    if ideal == 0:
        return 0.0
    return dcg([relevant.get(d, 0) for d in ranked[:k]]) / ideal


def reciprocal_rank(ranked: Sequence[str], relevant: dict[str, int], k: int) -> float:
    for rank, doc_id in enumerate(ranked[:k], start=1):
        if relevant.get(doc_id, 0) > 0:
            return 1.0 / rank
    return 0.0


def bootstrap_ci(
    values: Sequence[float], samples: int = 10_000, level: float = 0.95, seed: int = 13
) -> tuple[float, float]:
    data = np.asarray(values, dtype=float)
    if data.size == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    means = data[rng.integers(0, data.size, (samples, data.size))].mean(axis=1)
    tail = (1 - level) / 2
    return float(np.quantile(means, tail)), float(np.quantile(means, 1 - tail))


def permutation_test(
    a: Sequence[float], b: Sequence[float], samples: int = 20_000, seed: int = 13
) -> float:
    """Two-sided paired sign-flip test on the mean difference. Exact for up to 16 non-ties."""
    differences = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    differences = differences[differences != 0]
    n = differences.size
    if n == 0:
        return 1.0
    observed = abs(differences.mean())
    tolerance = 1e-12
    if n <= 16:
        signs = ((np.arange(2**n)[:, None] >> np.arange(n)) & 1) * 2 - 1
        return float(np.mean(np.abs((signs * differences).mean(axis=1)) >= observed - tolerance))
    rng = np.random.default_rng(seed)
    signs = rng.choice([-1.0, 1.0], size=(samples, n))
    extreme = np.sum(np.abs((signs * differences).mean(axis=1)) >= observed - tolerance)
    return float((extreme + 1) / (samples + 1))


def holm(p_values: Sequence[float]) -> list[float]:
    """Holm step-down adjustment for a family of comparisons."""
    order = sorted(range(len(p_values)), key=lambda i: p_values[i])
    adjusted = [0.0] * len(p_values)
    running = 0.0
    for position, index in enumerate(order):
        running = max(running, (len(p_values) - position) * p_values[index])
        adjusted[index] = min(1.0, running)
    return adjusted


@dataclass
class RunResult:
    name: str
    per_query: dict[str, dict[str, float]] = field(default_factory=dict)  # metric -> query -> value

    def values(self, metric: str, query_ids: Sequence[str]) -> list[float]:
        return [self.per_query[metric][q] for q in query_ids]


Ranker = Callable[[str], list[str]]


def evaluate_run(
    name: str, ranker: Ranker, queries: Sequence[Query], ks: Sequence[int] = (5, 10)
) -> RunResult:
    result = RunResult(name)
    for query in queries:
        ranked = ranker(query.text)
        for k in ks:
            result.per_query.setdefault(f"recall@{k}", {})[query.id] = recall_at(
                ranked, query.relevant, k
            )
            result.per_query.setdefault(f"ndcg@{k}", {})[query.id] = ndcg_at(
                ranked, query.relevant, k
            )
        result.per_query.setdefault("mrr@10", {})[query.id] = reciprocal_rank(
            ranked, query.relevant, 10
        )
    return result


def tune_alpha_cv(
    make_ranker: Callable[[float], Ranker],
    queries: Sequence[Query],
    alphas: Sequence[float] = (0.1, 0.3, 0.5, 0.7, 0.9),
    folds: int = 5,
    metric: str = "ndcg@10",
    seed: int = 13,
) -> tuple[RunResult, list[float]]:
    """Cross-validated linear fusion: each query is scored with an alpha tuned on other queries.

    Tuning alpha and reporting on the same queries would flatter this configuration.
    """
    runs = {a: evaluate_run(f"linear(a={a})", make_ranker(a), queries) for a in alphas}
    shuffled = list(queries)
    random.Random(seed).shuffle(shuffled)
    combined = RunResult("linear(cv)")
    chosen: list[float] = []
    for fold in range(folds):
        test = shuffled[fold::folds]
        test_ids = {q.id for q in test}
        train = [q.id for q in queries if q.id not in test_ids]
        best = max(alphas, key=lambda a: (np.mean(runs[a].values(metric, train)), -abs(a - 0.5)))
        chosen.append(best)
        for name, values in runs[best].per_query.items():
            for query_id in test_ids:
                combined.per_query.setdefault(name, {})[query_id] = values[query_id]
    return combined, chosen


def known_item_queries(
    documents: Sequence[Document], seed: int = 13, limit: int | None = None
) -> list[Query]:
    """Build queries without manual labels: a decision's summary should find that decision.

    The index must then be built WITHOUT summaries (`chunk_document(include_summary=False)`),
    or the query is matched against itself. Summaries read differently from real user queries,
    so treat this as a large, cheap regression signal and not as a measure of user success.
    """
    queries: list[Query] = []
    for document in documents:
        first = sentences(document.summary)[0] if document.summary.strip() else ""
        if len(first.split()) >= 5:
            queries.append(Query(f"ki-{document.id}", first, {document.id: 2}, "known_item"))
    random.Random(seed).shuffle(queries)
    return queries[:limit] if limit else queries


def summarise(
    runs: Sequence[RunResult], queries: Sequence[Query], baseline: str | None = None
) -> dict:
    query_ids = [q.id for q in queries]
    metrics = sorted({m for run in runs for m in run.per_query})
    summary: dict = {"n_queries": len(query_ids), "runs": {}, "comparisons": []}
    for run in runs:
        summary["runs"][run.name] = {}
        for metric in metrics:
            values = run.values(metric, query_ids)
            low, high = bootstrap_ci(values)
            summary["runs"][run.name][metric] = {
                "mean": float(np.mean(values)),
                "ci95": [low, high],
            }
    kinds = sorted({q.kind for q in queries})
    summary["by_kind"] = {
        kind: {
            "n": sum(q.kind == kind for q in queries),
            "ndcg@10": {
                run.name: float(
                    np.mean(run.values("ndcg@10", [q.id for q in queries if q.kind == kind]))
                )
                for run in runs
            },
        }
        for kind in kinds
    }
    base = next((r for r in runs if r.name == baseline), None)
    if base is not None:
        others = [run for run in runs if run.name != baseline]
        raw = [
            permutation_test(
                run.values("ndcg@10", query_ids), base.values("ndcg@10", query_ids)
            )
            for run in others
        ]
        for run, p_raw, p_holm in zip(others, raw, holm(raw), strict=True):
            run_values = run.values("ndcg@10", query_ids)
            base_values = base.values("ndcg@10", query_ids)
            differences = np.asarray(run_values) - np.asarray(base_values)
            low, high = bootstrap_ci(differences.tolist())
            summary["comparisons"].append(
                {
                    "run": run.name,
                    "baseline": baseline,
                    "metric": "ndcg@10",
                    "difference": float(differences.mean()),
                    "ci95": [low, high],
                    "wins": int((differences > 0).sum()),
                    "losses": int((differences < 0).sum()),
                    "ties": int((differences == 0).sum()),
                    "p": p_raw,
                    "p_holm": p_holm,
                }
            )
    return summary


def to_markdown(summary: dict, title: str, notes: Sequence[str] = ()) -> str:
    metrics = sorted({m for run in summary["runs"].values() for m in run})
    lines = [f"# {title}", ""]
    lines += [f"> {note}" for note in notes]
    lines += ["", f"Queries: {summary['n_queries']}. Brackets are 95% bootstrap intervals.", ""]
    lines.append("| Run | " + " | ".join(metrics) + " |")
    lines.append("| --- |" + " --- |" * len(metrics))
    for name, values in summary["runs"].items():
        cells = [
            f"{values[m]['mean']:.3f} [{values[m]['ci95'][0]:.2f}, {values[m]['ci95'][1]:.2f}]"
            for m in metrics
        ]
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    if summary["comparisons"]:
        lines += [
            "",
            "## Paired comparisons",
            "",
            "| Run vs baseline | Mean nDCG@10 diff | 95% CI | W/L/T | p | p (Holm) |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for c in summary["comparisons"]:
            lines.append(
                f"| {c['run']} vs {c['baseline']} | {c['difference']:+.3f} "
                f"| [{c['ci95'][0]:+.3f}, {c['ci95'][1]:+.3f}] "
                f"| {c['wins']}/{c['losses']}/{c['ties']} | {c['p']:.3f} | {c['p_holm']:.3f} |"
            )
    if len(summary["by_kind"]) > 1:
        names = list(summary["runs"])
        lines += ["", "## nDCG@10 by query type", ""]
        lines.append("| Type | n | " + " | ".join(names) + " |")
        lines.append("| --- | --- |" + " --- |" * len(names))
        for kind, row in summary["by_kind"].items():
            cells = [f"{row['ndcg@10'][name]:.3f}" for name in names]
            lines.append(f"| {kind} | {row['n']} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def save(summary: dict, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
