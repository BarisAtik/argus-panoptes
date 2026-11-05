import math

import numpy as np
import pytest
from conftest import make_document

from beacon import evaluate as ev
from beacon.cli import demo_path


def test_recall():
    assert ev.recall_at(["a", "b"], {"a": 2, "c": 1}, 2) == 0.5
    assert ev.recall_at(["b", "a"], {"a": 2}, 1) == 0.0


def test_recall_ignores_zero_grades():
    assert ev.recall_at(["a"], {"a": 2, "b": 0}, 5) == 1.0


def test_ndcg_by_hand():
    relevant = {"a": 2, "b": 1}
    assert ev.ndcg_at(["a", "b"], relevant, 2) == pytest.approx(1.0)
    ideal = 3 + 1 / math.log2(3)
    actual = 1 + 3 / math.log2(3)
    assert ev.ndcg_at(["b", "a"], relevant, 2) == pytest.approx(actual / ideal)
    assert ev.ndcg_at(["x"], relevant, 2) == 0.0


def test_ndcg_with_no_relevant_documents_is_zero():
    assert ev.ndcg_at(["a"], {}, 5) == 0.0


def test_reciprocal_rank():
    assert ev.reciprocal_rank(["x", "a"], {"a": 1}, 10) == 0.5
    assert ev.reciprocal_rank(["x"], {"a": 1}, 10) == 0.0


def test_bootstrap_interval_contains_the_mean_and_is_reproducible():
    values = list(np.linspace(0, 1, 30))
    low, high = ev.bootstrap_ci(values)
    assert low < np.mean(values) < high
    assert (low, high) == ev.bootstrap_ci(values)


def test_permutation_test_on_identical_runs_is_one():
    assert ev.permutation_test([0.5, 0.2], [0.5, 0.2]) == 1.0


def test_permutation_test_exact_value():
    # Five positive differences: only all-plus and all-minus are as extreme, 2 of 32.
    assert ev.permutation_test([1] * 5, [0] * 5) == pytest.approx(2 / 32)


def test_permutation_test_monte_carlo_detects_a_clear_difference():
    a = [1.0] * 40
    b = [0.0] * 40
    assert ev.permutation_test(a, b, samples=2000) < 0.01


def test_holm_by_hand():
    assert ev.holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])


def test_holm_caps_at_one():
    assert ev.holm([0.9, 0.8]) == pytest.approx([1.0, 1.0])


def test_check_labels_finds_dangling_ids():
    query = ev.Query("q", "x", {"known": 1, "gone": 2})
    assert ev.check_labels([query], {"known"}) == ["q: gone"]


def test_known_item_queries_need_a_usable_summary():
    documents = [
        make_document("a", summary="Dit is een lange en bruikbare samenvatting. Tweede zin hier."),
        make_document("b", summary="Kort."),
        make_document("c"),
    ]
    queries = ev.known_item_queries(documents)
    assert [q.relevant for q in queries] == [{"a": 2}]
    assert queries[0].text == "Dit is een lange en bruikbare samenvatting."


def test_cv_tuning_never_scores_a_query_with_its_own_tuning():
    queries = [ev.Query("q0", "q0", {"good": 2}), ev.Query("q1", "q1", {"good": 2})]

    def make_ranker(alpha):
        # Each alpha solves exactly one query, so the other query always tunes the wrong one.
        solved = "q0" if alpha == 0.1 else "q1"
        return lambda text: ["good"] if text == solved else ["bad"]

    combined, chosen = ev.tune_alpha_cv(make_ranker, queries, alphas=(0.1, 0.9), folds=2)
    assert sorted(chosen) == [0.1, 0.9]
    # Tuning on a set that includes the test query would solve at least one of them.
    assert combined.per_query["ndcg@10"] == {"q0": 0.0, "q1": 0.0}


def test_summary_and_report():
    queries = [ev.Query("q1", "a", {"x": 2}, "one"), ev.Query("q2", "b", {"y": 2}, "two")]
    good = ev.evaluate_run("good", lambda q: ["x", "y"], queries)
    bad = ev.evaluate_run("bad", lambda q: ["z"], queries)
    summary = ev.summarise([bad, good], queries, baseline="bad")
    assert summary["comparisons"][0]["wins"] == 2
    assert summary["by_kind"]["one"]["n"] == 1
    assert "good vs bad" in ev.to_markdown(summary, "Titel", ["Let op"])


def test_duplicate_query_ids_are_refused(tmp_path):
    path = tmp_path / "q.jsonl"
    line = '{"id":"a","query":"x","relevant":{}}\n'
    path.write_text(line * 2)
    with pytest.raises(ValueError):
        ev.load_queries(path)


def test_demo_labels_are_valid(demo_corpus):
    queries = ev.load_queries(demo_path("queries.jsonl"))
    assert ev.check_labels(queries, {d.id for d in demo_corpus}) == []
    assert {q.kind for q in queries} == {"lexical", "paraphrase", "unanswerable"}


def test_known_item_leak_is_visible(demo_corpus):
    """The reason for include_summary=False: with summaries indexed, the task is trivial."""
    from beacon.backends.local import LocalBackend
    from beacon.cli import index_documents
    from beacon.embeddings import HashingEmbedder
    from beacon.retrieval import Retriever

    def score(include_summary):
        backend = LocalBackend()
        embedder = HashingEmbedder(128)
        index_documents(backend, embedder, demo_corpus, include_summary=include_summary)
        retriever = Retriever(backend, embedder)
        queries = ev.known_item_queries(demo_corpus)
        rank = lambda q: [h.chunk.doc_id for h in retriever.search(q, "bm25", 10)]  # noqa: E731
        run = ev.evaluate_run("x", rank, queries)
        return np.mean(run.values("mrr@10", [q.id for q in queries]))

    assert score(True) > score(False)
