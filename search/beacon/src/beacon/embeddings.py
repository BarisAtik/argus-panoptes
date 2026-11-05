"""Embedders behind one small interface.

    st:<model>     sentence-transformers. Default multilingual-e5-small, the real thing.
    spacy:<model>  Mean of Dutch word vectors. A light, honest baseline.
    hash[:dims]    Hashed character n-grams. Offline and deterministic, for tests and CI.
                   It is a lexical method, so its numbers say nothing about semantic search.
"""

from __future__ import annotations

import hashlib
from typing import Protocol

import numpy as np

from .text import STOPWORDS


class Embedder(Protocol):
    name: str
    dims: int

    def embed_passages(self, texts: list[str]) -> np.ndarray: ...

    def embed_query(self, text: str) -> np.ndarray: ...


def _normalise(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=-1, keepdims=True)
    return matrix / np.where(norms == 0, 1.0, norms)


class HashingEmbedder:
    def __init__(self, dims: int = 512, ngrams: tuple[int, int] = (3, 5)):
        self.dims = dims
        self.ngrams = ngrams
        self.name = f"hash:{dims}"

    def _vector(self, text: str) -> np.ndarray:
        vector = np.zeros(self.dims, dtype=np.float32)
        padded = f" {' '.join(text.lower().split())} "
        for size in range(self.ngrams[0], self.ngrams[1] + 1):
            for start in range(len(padded) - size + 1):
                digest = hashlib.blake2b(padded[start : start + size].encode(), digest_size=8)
                value = int.from_bytes(digest.digest(), "little")
                vector[value % self.dims] += 1.0 if value >> 63 else -1.0
        return vector

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dims), dtype=np.float32)
        return _normalise(np.stack([self._vector(t) for t in texts]))

    def embed_query(self, text: str) -> np.ndarray:
        return _normalise(self._vector(text))


class SpacyEmbedder:
    def __init__(self, model: str = "nl_core_news_md"):
        import spacy

        unused = ["parser", "ner", "tagger", "lemmatizer", "morphologizer"]
        self.nlp = spacy.load(model, exclude=unused)
        self.dims = int(self.nlp.vocab.vectors_length)
        if not self.dims:
            raise ValueError(f"{model} has no word vectors")
        self.name = f"spacy:{model}"

    def _vector(self, text: str) -> np.ndarray:
        vectors = [
            token.vector
            for token in self.nlp.make_doc(text.lower())
            if token.is_alpha and token.text not in STOPWORDS and token.has_vector
        ]
        if not vectors:
            return np.zeros(self.dims, dtype=np.float32)
        return np.mean(vectors, axis=0)

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dims), dtype=np.float32)
        return _normalise(np.stack([self._vector(t) for t in texts]))

    def embed_query(self, text: str) -> np.ndarray:
        return _normalise(self._vector(text))


class SentenceTransformerEmbedder:
    def __init__(self, model: str = "intfloat/multilingual-e5-small", batch_size: int = 32):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model)
        self.batch_size = batch_size
        self.dims = int(self.model.get_sentence_embedding_dimension())
        self.name = f"st:{model}"
        # E5 models are trained with these prefixes. Without them quality drops silently.
        is_e5 = "e5" in model.lower()
        self.query_prefix = "query: " if is_e5 else ""
        self.passage_prefix = "passage: " if is_e5 else ""

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        return self.model.encode(
            [self.passage_prefix + t for t in texts],
            batch_size=self.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )

    def embed_query(self, text: str) -> np.ndarray:
        return self.model.encode(
            self.query_prefix + text, normalize_embeddings=True, convert_to_numpy=True
        )


def get_embedder(spec: str) -> Embedder:
    kind, _, arg = spec.partition(":")
    if kind == "hash":
        return HashingEmbedder(int(arg) if arg else 512)
    if kind == "spacy":
        return SpacyEmbedder(arg or "nl_core_news_md")
    if kind == "st":
        return SentenceTransformerEmbedder(arg) if arg else SentenceTransformerEmbedder()
    raise ValueError(f"unknown embedder {spec!r}: use st:<model>, spacy:<model> or hash[:dims]")
