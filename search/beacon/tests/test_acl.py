"""Access control must hold on every path, because one leaky path is a leak."""


import pytest

from beacon.backends.elastic import filter_clauses
from beacon.backends.local import LocalBackend
from beacon.cli import index_documents
from beacon.embeddings import HashingEmbedder
from beacon.mcp_server import build_server
from beacon.models import Document, Filters, Section
from beacon.rag import ExtractiveGenerator, answer
from beacon.retrieval import Retriever

SECRET = "ECLI:NL:XX:2025:9"
OPEN = "ECLI:NL:XX:2025:1"
SHARED = "ECLI:NL:XX:2025:5"
TEXT = "De fraude-afdeling onderzoekt de melding over het datalek bij de gemeente."


def corpus():
    return [
        Document(OPEN, "Open stuk", sections=[Section("A", ["Een openbare tekst over paden."])]),
        Document(SECRET, "Geheim stuk", sections=[Section("A", [TEXT])], acl=["fraude"]),
        Document(SHARED, "Gedeeld", sections=[Section("A", [TEXT])], acl=["fraude", "juridisch"]),
    ]  # fmt: skip


def retriever(groups):
    backend = LocalBackend()
    embedder = HashingEmbedder(64)
    index_documents(backend, embedder, corpus())
    return Retriever(backend, embedder, groups=groups)


PUBLIC_ONLY = frozenset({"public"})


@pytest.mark.parametrize("mode", ["bm25", "dense", "rrf", "linear"])
def test_search_never_returns_a_forbidden_document(mode):
    hits = retriever(PUBLIC_ONLY).search("fraude melding datalek gemeente", mode, 10)
    assert SECRET not in {h.chunk.doc_id for h in hits}
    assert SHARED not in {h.chunk.doc_id for h in hits}


def test_exact_lookup_cannot_bypass_the_filter():
    hits = retriever(PUBLIC_ONLY).search(f"zie {SECRET}", "rrf", 5)
    assert SECRET not in {h.chunk.doc_id for h in hits}
    allowed = retriever(frozenset({"fraude"})).search(f"zie {SECRET}", "rrf", 5)
    assert [h.chunk.doc_id for h in allowed] == [SECRET]


def test_get_document_treats_forbidden_as_missing():
    assert retriever(PUBLIC_ONLY).document(SECRET) == []
    assert retriever(PUBLIC_ONLY).document("nope") == []
    assert retriever(frozenset({"fraude"})).document(SECRET)


def test_rag_contexts_are_filtered():
    result = answer(TEXT, retriever(PUBLIC_ONLY), ExtractiveGenerator())
    assert SECRET not in {h.chunk.doc_id for h in result.contexts}
    assert "fraude-afdeling" not in result.text


def test_one_shared_group_is_enough():
    found = {h.chunk.doc_id for h in retriever(frozenset({"juridisch"})).search(TEXT, "bm25", 5)}
    assert found == {SHARED}


def test_empty_groups_see_nothing_at_all():
    nobody = retriever(frozenset())
    assert nobody.search("paden", "rrf", 5) == []
    assert nobody.document(OPEN) == []


def test_caller_filters_cannot_widen_the_scope():
    wide = Filters(groups=frozenset({"fraude"}))
    hits = retriever(PUBLIC_ONLY).search(TEXT, "bm25", 5, wide)
    assert SECRET not in {h.chunk.doc_id for h in hits}


def test_no_groups_means_trusted_operator():
    assert retriever(None).document(SECRET)


async def test_mcp_tools_cannot_reach_forbidden_documents_or_change_groups():
    from mcp import Client

    server = build_server(retriever(PUBLIC_ONLY), ExtractiveGenerator())
    async with Client(server) as client:
        tools = (await client.list_tools()).tools
        for tool in tools:
            assert "groups" not in tool.input_schema.get("properties", {})
        found = await client.call_tool("search", {"query": TEXT, "mode": "bm25"})
        assert SECRET not in str(found)
        missing = await client.call_tool("get_document", {"doc_id": SECRET})
        assert missing.is_error


def test_elastic_filter_is_terms_and_empty_groups_stay_a_filter():
    assert filter_clauses(Filters(groups=frozenset({"b", "a"}))) == [{"terms": {"acl": ["a", "b"]}}]
    assert filter_clauses(Filters(groups=frozenset())) == [{"terms": {"acl": []}}]
    assert filter_clauses(Filters()) == []
