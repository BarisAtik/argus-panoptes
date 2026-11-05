import httpx
import pytest

from beacon.models import read_corpus
from beacon.sources.rechtspraak import (
    ParseError,
    RechtspraakClient,
    fetch_corpus,
    parse_document,
    parse_feed,
)


def client_for(handler, **kwargs):
    http = httpx.Client(base_url="https://test", transport=httpx.MockTransport(handler))
    return RechtspraakClient(http, requests_per_second=10, sleep=lambda _: None, **kwargs)


@pytest.fixture
def document_xml(fixtures):
    return (fixtures / "document.xml").read_bytes()


@pytest.fixture
def feed_xml(fixtures):
    return (fixtures / "feed.xml").read_bytes()


def test_parses_metadata(document_xml):
    document = parse_document(document_xml)
    assert document.id == "ECLI:NL:XX:2025:999"
    assert document.court == "Rechtbank Noordkust"
    assert document.date == "2025-01-15"
    assert document.doc_type == "Uitspraak"
    assert document.subjects == ["Civiel recht", "Huurrecht"]
    assert document.case_numbers == ["NK/123", "NK/124"]
    assert document.place == "Noordkust"
    assert document.summary == "Huurverhoging kwam te laat."
    assert document.title.startswith("ECLI:NL:XX:2025:999 Rechtbank")


def test_parses_nested_sections_in_reading_order(document_xml):
    sections = parse_document(document_xml).sections
    assert [s.title for s in sections] == [
        "1 De feiten",
        "2 De beoordeling",
        "2.2 Nadere overweging",
        "beslissing",
    ]
    assert sections[1].paragraphs == ["2.1 Het voorstel was niet tijdig gedaan."]


def test_names_of_people_are_not_parsed(document_xml):
    document = parse_document(document_xml)
    everything = str(document)
    assert "Testnaam" not in everything


def test_rejects_entity_expansion():
    xml = b"""<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x SYSTEM "file:///etc/passwd">]>
    <open-rechtspraak xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
      xmlns:dcterms="http://purl.org/dc/terms/"><rdf:RDF><rdf:Description>
      <dcterms:identifier>ECLI:NL:XX:2025:1</dcterms:identifier>
      <dcterms:creator>&x;</dcterms:creator></rdf:Description></rdf:RDF></open-rechtspraak>"""
    try:
        document = parse_document(xml)
    except ParseError:
        return
    assert "root:" not in document.court


@pytest.mark.parametrize("xml", [b"not xml", b"<a/>", b"<a xmlns:r='x'></a>"])
def test_bad_input_raises_parse_error(xml):
    with pytest.raises(ParseError):
        parse_document(xml)


def test_placeholder_summary_is_treated_as_missing(document_xml):
    xml = document_xml.replace(b"Huurverhoging kwam te laat.", b"Geen inhoudsindicatie")
    assert parse_document(xml).summary == ""


def test_feed_marks_deleted_entries(feed_xml):
    entries = parse_feed(feed_xml)
    assert [e.ecli for e in entries] == [f"ECLI:NL:XX:2025:{n}" for n in (1, 2, 3)]
    assert entries[1].deleted == "doc"


def test_search_pages_skips_deleted_and_survives_overlapping_pages(feed_xml):
    requests = []

    def handler(request):
        requests.append(dict(request.url.params.multi_items()))
        # The server repeats the same page: the client must stop instead of looping.
        return httpx.Response(200, content=feed_xml)

    entries = list(client_for(handler).search(date_from="2025-01-01", date_to="2025-01-31"))
    assert [e.ecli for e in entries] == ["ECLI:NL:XX:2025:1", "ECLI:NL:XX:2025:3"]
    assert len(requests) == 2
    assert requests[0]["return"] == "DOC"


def test_date_range_sends_two_date_parameters(feed_xml):
    seen = {}

    def handler(request):
        seen["date"] = request.url.params.get_list("date")
        return httpx.Response(200, content=b'<feed xmlns="http://www.w3.org/2005/Atom"/>')

    list(client_for(handler).search(date_from="2025-01-01", date_to="2025-01-31"))
    assert seen["date"] == ["2025-01-01", "2025-01-31"]


def test_retries_server_errors_then_succeeds(feed_xml):
    responses = iter([httpx.Response(503), httpx.Response(200, content=feed_xml)])
    client = client_for(lambda request: next(responses))
    assert client._get("/uitspraken/zoeken", []) == feed_xml


def test_gives_up_after_max_retries():
    client = client_for(lambda request: httpx.Response(503), max_retries=2)
    with pytest.raises(httpx.HTTPStatusError):
        client._get("/x", [])


def test_client_errors_are_not_retried():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(400)

    with pytest.raises(httpx.HTTPStatusError):
        client_for(handler)._get("/x", [])
    assert len(calls) == 1


def test_rate_above_the_service_limit_is_refused():
    with pytest.raises(ValueError):
        RechtspraakClient(httpx.Client(), requests_per_second=11)


def test_content_uses_the_cache(tmp_path, document_xml):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, content=document_xml)

    client = client_for(handler, cache_dir=tmp_path)
    assert client.content("ECLI:NL:XX:2025:999") == client.content("ECLI:NL:XX:2025:999")
    assert len(calls) == 1


def test_fetch_counts_bad_documents_and_keeps_going(tmp_path, feed_xml, document_xml):
    def handler(request):
        if "zoeken" in request.url.path:
            return httpx.Response(200, content=feed_xml)
        good = request.url.params["id"].endswith(":1")
        return httpx.Response(200, content=document_xml if good else b"<broken")

    output = tmp_path / "corpus.jsonl"
    counts = fetch_corpus(client_for(handler), output, "2025-01-01", "2025-01-31")
    assert counts == {"written": 1, "parse_errors": 1, "empty": 0}
    assert read_corpus(output)[0].id == "ECLI:NL:XX:2025:999"
