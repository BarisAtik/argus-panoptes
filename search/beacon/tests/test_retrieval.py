import numpy as np
import pytest
from conftest import make_chunk

from beacon.backends.local import LocalBackend
from beacon.embeddings import HashingEmbedder
from beacon.models import Filters, Hit
from beacon.retrieval import Retriever, collapse, linear_fuse, rrf_fuse


def hit(chunk_id, score=1.0, doc_id=None, highlight=""):
    return Hit(make_chunk(chunk_id, doc_id or chunk_id), score, highlight)


def ids(hits):
    return [h.chunk.id for h in hits]


def test_rrf_scores_follow_the_formula():
    fused = rrf_fuse([[hit("a"), hit("b")], [hit("b"), hit("c")]], rrf_k=60)
    assert ids(fused) == ["b", "a", "c"]
    assert fused[0].score == pytest.approx(1 / 62 + 1 / 61)
    assert fused[1].score == pytest.approx(1 / 61)


def test_rrf_keeps_the_highlight():
    fused = rrf_fuse([[hit("a")], [hit("a", highlight="<em>x</em>")]])
    assert fused[0].highlight == "<em>x</em>"


def test_rrf_handles_an_empty_list():
    assert ids(rrf_fuse([[], [hit("a")]])) == ["a"]


def test_linear_extremes_reduce_to_one_ranking():
    lexical = [hit("a", 10), hit("b", 1)]
    dense = [hit("b", 0.9), hit("a", 0.1)]
    assert ids(linear_fuse(lexical, dense, alpha=1.0)) == ["a", "b"]
    assert ids(linear_fuse(lexical, dense, alpha=0.0)) == ["b", "a"]


def test_linear_is_not_dominated_by_score_scale():
    lexical = [hit("a", 1000), hit("b", 900)]
    dense = [hit("b", 0.9), hit("a", 0.1)]
    assert ids(linear_fuse(lexical, dense, alpha=0.5))[0] in {"a", "b"}
    assert linear_fuse(lexical, dense, alpha=0.5)[0].score == pytest.approx(0.5)


def test_linear_rejects_bad_alpha():
    with pytest.raises(ValueError):
        linear_fuse([], [], alpha=1.5)


def test_collapse_keeps_the_best_chunk_per_document():
    hits = [hit("a#0", doc_id="a"), hit("a#1", doc_id="a"), hit("b#0", doc_id="b")]
    assert ids(collapse(hits, 10)) == ["a#0", "b#0"]
    assert ids(collapse(hits, 1)) == ["a#0"]


def test_local_bm25_prefers_rare_terms():
    backend = LocalBackend()
    backend.create(4)
    backend.add(
        [
            make_chunk("1", "1", "huur huur woning"),
            make_chunk("2", "2", "woning tuin"),
            make_chunk("3", "3", "woning garage"),
        ],
        np.eye(3, 4, dtype=np.float32),
    )
    assert backend.lexical("huur", 3)[0].chunk.id == "1"
    assert len(backend.lexical("huur", 3)) == 1


def test_local_stemming_matches_inflected_forms():
    backend = LocalBackend()
    backend.create(2)
    backend.add([make_chunk("1", "1", "de verhuurders")], np.zeros((1, 2), np.float32))
    assert backend.lexical("verhuurder", 1)


def test_local_dense_and_lexical_apply_filters():
    backend = LocalBackend()
    embedder = HashingEmbedder(32)
    chunks = [
        make_chunk("1", "1", "huur woning", court="A", date="2024-01-01"),
        make_chunk("2", "2", "huur woning", court="B", date="2025-01-01"),
    ]
    backend.create(32)
    backend.add(chunks, embedder.embed_passages([c.text for c in chunks]))
    filters = Filters(court="B")
    assert ids(backend.lexical("huur", 5, filters)) == ["2"]
    assert ids(backend.dense(embedder.embed_query("huur"), 5, filters)) == ["2"]
    assert ids(backend.lexical("huur", 5, Filters(date_to="2024-06-01"))) == ["1"]
    assert ids(backend.lexical("huur", 5, Filters(date_from="2024-06-01"))) == ["2"]


def test_adding_mismatched_lengths_fails():
    backend = LocalBackend()
    backend.create(2)
    with pytest.raises(ValueError):
        backend.add([make_chunk()], np.zeros((2, 2), np.float32))


@pytest.mark.parametrize("mode", ["bm25", "dense", "rrf", "linear"])
def test_every_mode_returns_unique_documents(demo_retriever, mode):
    hits = demo_retriever.search("huurder en verhuurder", mode, 5)
    assert 0 < len(hits) <= 5
    assert len({h.chunk.doc_id for h in hits}) == len(hits)


def test_ecli_in_the_query_is_resolved_exactly(demo_retriever, demo_corpus):
    target = demo_corpus[4].id
    hits = demo_retriever.search(f"zoek {target.lower()} graag")
    assert hits[0].chunk.doc_id == target


def test_ecli_lookup_respects_filters(demo_retriever, demo_corpus):
    target = demo_corpus[0]
    hits = demo_retriever.search(target.id, filters=Filters(court="Bestaat Niet"))
    assert hits == []


def test_blank_query_returns_nothing(demo_retriever):
    assert demo_retriever.search("   ") == []


def test_unknown_mode_is_rejected(demo_retriever):
    with pytest.raises(ValueError):
        demo_retriever.search("huur", "magic")


def test_empty_embedder_vector_does_not_crash():
    backend = LocalBackend()
    embedder = HashingEmbedder(16)
    retriever = Retriever(backend, embedder)
    backend.create(16)
    assert retriever.search("huur") == []
