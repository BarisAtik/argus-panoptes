"""Against a live engine.

Run with: BEACON_IT=1 ES_URL=... ELASTIC_PASSWORD=... pytest -m integration
"""

import os
from dataclasses import replace

import pytest

from beacon.backends.elastic import ElasticBackend
from beacon.cli import embed_and_add, index_documents
from beacon.config import Settings
from beacon.embeddings import HashingEmbedder
from beacon.models import Chunk, Filters
from beacon.retrieval import Retriever

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.getenv("BEACON_IT"), reason="set BEACON_IT=1 and start a server"),
]


@pytest.fixture(scope="module")
def retriever():
    from beacon.cli import demo_path
    from beacon.models import read_corpus

    settings = Settings.from_env()
    backend = ElasticBackend.from_settings(
        Settings(settings.es_url, settings.es_user, settings.es_password, "beacon-it")
    )
    embedder = HashingEmbedder(64)
    index_documents(backend, embedder, read_corpus(demo_path("corpus.jsonl")), recreate=True)
    yield Retriever(backend, embedder)
    backend.client.indices.delete(index="beacon-it")


def test_stats(retriever):
    stats = retriever.backend.stats()
    assert stats["documents"] == 35
    assert stats["chunks"] >= 35


def test_dutch_analyzer_stems_and_highlights(retriever):
    # "verhuurders" only matches "verhuurder" in the text through stemming.
    hits = retriever.backend.lexical("verhuurders", 5)
    assert hits
    assert any("verhuurder" in hit.chunk.text.lower() for hit in hits)
    assert "<em>" in retriever.backend.lexical("huurachterstand", 3)[0].highlight


@pytest.mark.parametrize("mode", ["bm25", "dense", "rrf", "linear"])
def test_each_mode_returns_documents(retriever, mode):
    assert retriever.search("huurachterstand ontruiming", mode, 3)


def test_filters_apply_to_both_retrievers(retriever):
    filters = Filters(court="Rechtbank Noordkust", date_from="2025-01-01")
    for mode in ("bm25", "dense"):
        hits = retriever.search("woning", mode, 10, filters)
        assert hits
        assert {h.chunk.court for h in hits} == {"Rechtbank Noordkust"}
        assert all(h.chunk.date >= "2025-01-01" for h in hits)


def test_document_chunks_are_ordered(retriever):
    chunks = retriever.document("ECLI:NL:XX:2025:1")
    assert [c.position for c in chunks] == sorted(c.position for c in chunks)


def test_ingest_is_idempotent(retriever):
    chunks = retriever.document("ECLI:NL:XX:2025:1")
    before = retriever.backend.stats()["chunks"]
    embed_and_add(retriever.backend, retriever.embedder, chunks)
    assert retriever.backend.stats()["chunks"] == before


def test_access_filter_runs_on_the_engine(retriever):
    nobody = Filters(groups=frozenset({"some-other-group"}))
    assert retriever.search("woning", "rrf", 5, nobody) == []
    everyone = Filters(groups=frozenset({"public"}))
    assert retriever.search("woning", "rrf", 5, everyone)


def test_refs_are_filtered_on_the_engine(retriever):
    backend = retriever.backend
    chunk = Chunk("ref#0", "ref", 0, "", "pagina", acl=["juristen"], refs=["avg", "avg:22"])
    embed_and_add(backend, retriever.embedder, [chunk])
    assert [h.chunk.doc_id for h in backend.by_refs(["avg:22"], 5)] == ["ref"]
    assert backend.by_refs(["avg:22"], 5)[0].chunk.refs == ["avg", "avg:22"]
    assert backend.by_refs(["avg:22"], 5, Filters(groups=frozenset({"public"}))) == []
    assert backend.by_refs(["avg:23"], 5) == []


def test_term_coverage_uses_dutch_analysis(retriever):
    assert retriever.backend.term_coverage("huurachterstand") == 1.0
    assert retriever.backend.term_coverage("huurachterstand xyzzyplugh") == 0.5
    assert retriever.backend.term_coverage("xyzzyplugh") == 0.0


def test_smart_mode_on_the_engine(retriever):
    full = replace(retriever, routing="coverage", synonyms=True, refs=True)
    assert full.search("huurachterstand ontruiming", "smart", 3)
    nobody = replace(full, groups=frozenset({"some-other-group"}))
    assert nobody.search("artikel 22 AVG", "smart", 3) == []


def test_delete_document_removes_every_chunk(retriever):
    chunks = [Chunk(f"weg#{i}", "weg", i, "", "tijdelijk", acl=["public"]) for i in range(3)]
    embed_and_add(retriever.backend, retriever.embedder, chunks)
    assert len(retriever.document("weg")) == 3
    retriever.backend.delete_document("weg")
    assert retriever.document("weg") == []
