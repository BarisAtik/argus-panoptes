from conftest import make_chunk

from beacon.backends.elastic import analysis_settings, index_body
from beacon.backends.local import LocalBackend
from beacon.compounds import Decompounder, build_vocabulary
from beacon.embeddings import HashingEmbedder
from beacon.text import tokens

VOCABULARY = {"algoritme": 40, "register": 30, "gegevens": 50, "bescherming": 20, "effect": 9,
              "beoordeling": 15, "taal": 5, "model": 9}  # fmt: skip


def test_splits_known_parts_and_linking_s():
    splitter = Decompounder(VOCABULARY)
    assert splitter.split("algoritmeregister") == ["algoritme", "register"]
    assert splitter.split("gegevensbeschermingseffectbeoordeling") == [
        "gegevens", "bescherming", "effect", "beoordeling",
    ]  # fmt: skip


def test_leaves_short_and_unknown_words_alone():
    splitter = Decompounder(VOCABULARY)
    assert splitter.split("taalmodel") == ["taal", "model"]
    assert splitter.split("model") == []
    assert splitter.split("onbekendwoord") == []
    assert splitter.split("registerzzz") == []


def test_prefers_fewer_parts():
    vocabulary = {"fietspad": 5, "fiets": 5, "pads": 5, "plan": 9}
    splitter = Decompounder(vocabulary)
    assert splitter.split("fietspadplan") == ["fietspad", "plan"]


def test_vocabulary_needs_two_texts_and_skips_stop_words():
    vocabulary = build_vocabulary(["register alleen hier", "register tegen", "tegen uniek"])
    assert "register" in vocabulary
    assert "uniek" not in vocabulary
    assert "tegen" not in vocabulary


def test_tokens_keep_the_compound_and_add_its_parts():
    splitter = Decompounder(VOCABULARY)
    produced = tokens("het algoritmeregister", splitter)
    assert produced[0] == tokens("algoritmeregister")[0]
    assert tokens("register")[0] in produced
    assert tokens("algoritme")[0] in produced


def test_bm25_finds_the_part_only_with_compounds():
    chunks = [make_chunk("a#0", "a", "het algoritmeregister van de overheid"),
              make_chunk("b#0", "b", "een ander onderwerp over fietsen")]  # fmt: skip
    embedder = HashingEmbedder(8)
    plain = LocalBackend()
    plain.add(chunks, embedder.embed_passages([c.text for c in chunks]))
    assert plain.lexical("register", 5) == []
    split = LocalBackend(decompounder=Decompounder(VOCABULARY))
    split.add(chunks, embedder.embed_passages([c.text for c in chunks]))
    assert [h.chunk.doc_id for h in split.lexical("register", 5)] == ["a"]


def test_lucene_chain_decompounds_before_stemming():
    settings = analysis_settings(["register"])["analysis"]
    chain = settings["analyzer"]["dutch_compound"]["filter"]
    assert chain.index("dutch_compounds") < chain.index("dutch_stemmer")
    assert settings["filter"]["dutch_compounds"]["word_list"] == ["register"]


def test_index_body_switches_analyzer_only_with_a_word_list():
    assert index_body(8)["mappings"]["properties"]["text"]["analyzer"] == "dutch"
    body = index_body(8, ["register"])
    assert body["mappings"]["properties"]["text"]["analyzer"] == "dutch_compound"
    assert "analysis" not in index_body(8)["settings"]


def test_a_linker_alone_is_not_a_compound():
    assert Decompounder({"aanbieder": 5}).split("aanbieders") == []
