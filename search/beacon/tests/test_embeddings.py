import sys
import types

import numpy as np
import pytest

from beacon.embeddings import HashingEmbedder, get_embedder


def test_hash_embedder_is_deterministic_and_normalised():
    embedder = HashingEmbedder(64)
    first = embedder.embed_query("huurovereenkomst")
    assert np.array_equal(first, embedder.embed_query("huurovereenkomst"))
    assert np.linalg.norm(first) == pytest.approx(1.0, abs=1e-5)


def test_hash_embedder_sees_shared_character_ngrams():
    embedder = HashingEmbedder(512)
    query = embedder.embed_query("huurovereenkomst")
    near, far = embedder.embed_passages(["de huurovereenkomsten", "vissoorten in het meer"])
    assert query @ near > query @ far


def test_empty_inputs():
    embedder = HashingEmbedder(8)
    assert embedder.embed_passages([]).shape == (0, 8)
    assert not np.isnan(embedder.embed_query("")).any()


def test_unknown_spec():
    with pytest.raises(ValueError):
        get_embedder("word2vec:x")


def test_e5_gets_its_query_and_passage_prefixes(monkeypatch):
    seen = []

    class FakeModel:
        def __init__(self, name):
            pass

        def get_sentence_embedding_dimension(self):
            return 2

        def encode(self, texts, **kwargs):
            seen.append(texts)
            return np.zeros(2)

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        types.SimpleNamespace(SentenceTransformer=FakeModel),
    )
    embedder = get_embedder("st:intfloat/multilingual-e5-small")
    embedder.embed_query("vraag")
    embedder.embed_passages(["tekst"])
    assert seen == ["query: vraag", ["passage: tekst"]]

    seen.clear()
    get_embedder("st:other/model").embed_query("vraag")
    assert seen == ["vraag"]
