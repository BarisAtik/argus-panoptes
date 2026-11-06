import numpy as np
import pytest

from beacon.backends.local import LocalBackend
from beacon.citations import article_refs, extract_refs
from beacon.embeddings import HashingEmbedder
from beacon.models import Chunk, Filters
from beacon.retrieval import Retriever, rrf_fuse
from beacon.routing import detect_dutch, lexical_weight
from beacon.sources.algoritmekader import source_refs
from beacon.synonyms import expand


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("artikel 22 AVG", {"avg", "avg:22"}),
        ("art. 22 GDPR", {"avg", "avg:22"}),
        ("Article 22 of the General Data Protection Regulation", {"avg", "avg:22"}),
        ("AVG artikel 22", {"avg", "avg:22"}),
        ("artikel 14 AI-verordening", {"aia", "aia:14"}),
        ("Artikel 9(6 en 8) Verordening Artificiële Intelligentie", {"aia", "aia:9"}),
        ("Artikel 5 lid 1 onder c Algemene Verordening Gegevensbescherming", {"avg", "avg:5"}),
        ("Artikel 3:46 Awb", {"awb", "awb:3:46"}),
        ("Archiefwet bewaartermijn", {"archiefwet"}),
        ("artikel 5 van de Grondwet", {"grondwet", "grondwet:5"}),
        ("Verordening (EU) 2024/1689", {"aia"}),
        ("een woord dat niets citeert", set()),
        ("artikel 7 van deze tekst", set()),
    ],
)
def test_extract_refs(text, expected):
    assert set(extract_refs(text)) == expected


def test_article_range_is_expanded():
    refs = extract_refs("Artikel 15 - 21 Algemene Verordening Gegevensbescherming")
    assert {f"avg:{n}" for n in range(15, 22)} <= set(refs)


def test_law_name_inside_a_word_does_not_count():
    assert extract_refs("biowet, woonhuis, kawoord") == []


def test_article_refs_drops_bare_laws():
    assert article_refs(["avg", "avg:22"]) == ["avg:22"]


def test_source_refs_reads_only_the_sources_section():
    body = (
        "## Vereiste\n\nZie artikel 1 AVG.\n\n## Bronnen\n\n"
        "- [Artikel 14 verordening Artificiële Intelligentie](https://example.org/x)\n\n"
        "## Risico\n\nArtikel 3 Awb.\n"
    )
    assert source_refs(body) == ["aia", "aia:14"]


def test_expand_adds_the_other_terms_of_a_group():
    assert "gegevensbeschermingseffectbeoordeling" in expand("wanneer moet een DPIA")
    assert expand("iets zonder afkorting") == "iets zonder afkorting"
    # `bio` inside a word is not the abbreviation.
    assert "baseline" not in expand("biologie")


def test_detect_dutch_with_a_fake_frequency_table():
    table = {("de", "nl"): 7, ("the", "en"): 7, ("wet", "nl"): 5, ("law", "en"): 5}
    lookup = lambda word, lang: table.get((word, lang), 0)  # noqa: E731
    assert detect_dutch("de wet", lookup)
    assert not detect_dutch("the law", lookup)
    assert detect_dutch("", lookup)


def test_lexical_weight_methods():
    assert lexical_weight("x", "none", lambda _: 0.0) == 1.0
    assert lexical_weight("x", "coverage", lambda _: 0.5, power=2) == 0.25
    with pytest.raises(ValueError):
        lexical_weight("x", "magic", lambda _: 0.0)


def test_rrf_weight_zero_ignores_a_list():
    def hit(name):
        from beacon.models import Hit

        return Hit(Chunk(name, name, 0, "", ""), 1.0)

    fused = rrf_fuse([[hit("a")], [hit("b")]], weights=[0.0, 1.0])
    assert [h.chunk.id for h in fused] == ["b"]


def stack(**options) -> Retriever:
    embedder = HashingEmbedder()
    backend = LocalBackend()
    chunks = [
        Chunk("a#0", "a", 0, "", "toezicht door mensen", acl=["x"], refs=["aia", "aia:14"]),
        Chunk("a#1", "a", 1, "", "meer toezicht", acl=["x"], refs=["aia", "aia:14"]),
        Chunk("b#0", "b", 0, "", "gegevensbeschermingseffectbeoordeling verplicht", acl=["y"]),
        Chunk("c#0", "c", 0, "", "iets heel anders", acl=["y"]),
    ]
    backend.add(chunks, embedder.embed_passages([c.text for c in chunks]))
    return Retriever(backend, embedder, **options)


def test_term_coverage():
    backend = stack().backend
    assert backend.term_coverage("toezicht") == 1.0
    assert backend.term_coverage("toezicht xyzzy") == 0.5
    assert backend.term_coverage("") == 0.0


def test_by_refs_returns_each_document_once_and_respects_filters():
    backend = stack().backend
    assert [h.chunk.id for h in backend.by_refs(["aia:14"], 10)] == ["a#0"]
    denied = Filters(groups=frozenset({"y"}))
    assert backend.by_refs(["aia:14"], 10, denied) == []


def test_smart_uses_refs_and_synonyms_only_when_enabled():
    with_refs = stack(refs=True)
    assert with_refs.search("artikel 14 AI-verordening", "smart")[0].chunk.doc_id == "a"
    synonyms = stack(synonyms=True, candidates=1)
    assert synonyms.backend.lexical("dpia", 5) == []
    ids = [h.chunk.doc_id for h in synonyms.chunks("dpia", "smart")]
    assert "b" in ids


def test_smart_never_leaks_through_refs():
    scoped = stack(refs=True, groups=frozenset({"y"}))
    assert all(h.chunk.doc_id != "a" for h in scoped.search("artikel 14 AI-verordening", "smart"))


def test_coverage_routing_drops_lexical_when_nothing_matches():
    retriever = stack(routing="coverage")
    calls = []
    original = retriever.backend.lexical
    retriever.backend.lexical = lambda *a, **k: calls.append(a) or original(*a, **k)
    retriever.chunks("xyzzy plugh", "smart")
    assert calls == []
    assert isinstance(retriever.embedder.embed_query("x"), np.ndarray)


def test_delete_document():
    backend = stack().backend
    backend.delete_document("a")
    assert backend.document_chunks("a") == []
    assert backend.document_chunks("b")
    found = backend.lexical("gegevensbeschermingseffectbeoordeling", 5)
    assert [hit.chunk.doc_id for hit in found] == ["b"]
