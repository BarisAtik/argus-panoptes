import json

import pytest
from mcp import Client

from beacon.mcp_server import MAX_RESULTS, build_server
from beacon.rag import ExtractiveGenerator


@pytest.fixture
def server(demo_retriever):
    return build_server(demo_retriever, ExtractiveGenerator())


def payload(result):
    assert not result.is_error, result
    if result.structured_content is not None:
        return result.structured_content
    return json.loads(result.content[0].text)


async def test_tools_are_listed_and_read_only(server):
    async with Client(server) as client:
        tools = (await client.list_tools()).tools
    assert {t.name for t in tools} == {"search", "get_document", "ask", "index_info"}
    assert all(t.annotations.read_only_hint for t in tools)
    assert all(t.description for t in tools)


async def test_search_returns_marked_untrusted_text(server):
    async with Client(server) as client:
        result = payload(await client.call_tool("search", {"query": "huurachterstand", "k": 3}))
    assert 0 < len(result["results"]) <= 3
    assert result["results"][0]["doc_id"].startswith("ECLI:NL:XX:")
    assert result["results"][0]["untrusted_text"]


async def test_search_applies_filters(server):
    async with Client(server) as client:
        result = payload(
            await client.call_tool("search", {"query": "woning", "court": "Rechtbank Noordkust"})
        )
    assert {r["court"] for r in result["results"]} == {"Rechtbank Noordkust"}


async def test_search_caps_k(server):
    async with Client(server) as client:
        result = payload(await client.call_tool("search", {"query": "woning", "k": 500}))
    assert len(result["results"]) == MAX_RESULTS


async def test_search_rejects_unknown_mode(server):
    async with Client(server) as client:
        result = await client.call_tool("search", {"query": "x", "mode": "magic"})
    assert result.is_error


async def test_get_document(server, demo_corpus):
    target = demo_corpus[0]
    async with Client(server) as client:
        result = payload(await client.call_tool("get_document", {"doc_id": target.id}))
        missing = await client.call_tool("get_document", {"doc_id": "ECLI:NL:XX:1999:0"})
    assert result["court"] == target.court
    assert "woning" in result["untrusted_text"]
    assert missing.is_error


async def test_ask_answers_and_abstains(server):
    async with Client(server) as client:
        question = "Wanneer mag een verhuurder de huur verhogen?"
        good = payload(await client.call_tool("ask", {"question": question}))
        none = payload(await client.call_tool("ask", {"question": "Welke vissoorten leven hier?"}))
    assert good["grounded"] and not good["abstained"] and "[" in good["answer"]
    assert none["abstained"]


async def test_index_info(server, demo_corpus):
    async with Client(server) as client:
        result = payload(await client.call_tool("index_info", {}))
    assert result["documents"] == len(demo_corpus)
    assert result["embedder"].startswith("hash")
