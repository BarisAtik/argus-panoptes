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


def test_cache_reuses_vectors_and_keeps_order(tmp_path):
    from beacon.embeddings import CachedEmbedder, HashingEmbedder

    class Counting(HashingEmbedder):
        calls = 0

        def embed_passages(self, texts):
            Counting.calls += len(texts)
            return super().embed_passages(texts)

    plain = HashingEmbedder(32)
    cached = CachedEmbedder(Counting(32), tmp_path)
    first = cached.embed_passages(["a b c", "d e f", "a b c"])
    assert Counting.calls == 2
    again = CachedEmbedder(Counting(32), tmp_path).embed_passages(["d e f", "a b c"])
    assert Counting.calls == 2
    assert np.allclose(first[0], plain.embed_passages(["a b c"])[0])
    assert np.allclose(again[0], first[1])
    assert cached.embed_passages([]).shape == (0, 32)


def test_onnx_spec_reports_a_missing_model(tmp_path):
    import pytest

    pytest.importorskip("onnxruntime")
    with pytest.raises(FileNotFoundError):
        get_embedder(f"onnx:{tmp_path}")
