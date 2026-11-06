"""Embedders behind one small interface.

    st:<model>     sentence-transformers. Default multilingual-e5-small, the real thing.
    onnx:<dir>     The same model family as quantised ONNX, no torch. See `beacon fetch-model`.
    spacy:<model>  Mean of Dutch word vectors. A light, honest baseline.
    hash[:dims]    Hashed character n-grams. Offline and deterministic, for tests and CI.
                   It is a lexical method, so its numbers say nothing about semantic search.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from pathlib import Path
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


class OnnxEmbedder:
    """Mean-pooled sentence embeddings from an ONNX export, on CPU, without torch."""

    def __init__(self, directory: str, batch_size: int = 16, max_tokens: int = 512):
        import onnxruntime
        from tokenizers import Tokenizer

        folder = Path(directory)
        models = sorted(folder.glob("*.onnx"))
        if not models:
            raise FileNotFoundError(f"no .onnx file in {folder}; run `beacon fetch-model`")
        self.tokenizer = Tokenizer.from_file(str(folder / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=max_tokens)
        self.session = onnxruntime.InferenceSession(
            str(models[0]), providers=["CPUExecutionProvider"]
        )
        self.inputs = {item.name for item in self.session.get_inputs()}
        self.batch_size = batch_size
        self.dims = int(self.session.get_outputs()[0].shape[-1] or 384)
        self.name = f"onnx:{folder.name}"
        is_e5 = "e5" in folder.name.lower()
        self.query_prefix = "query: " if is_e5 else ""
        self.passage_prefix = "passage: " if is_e5 else ""

    def _encode(self, texts: list[str]) -> np.ndarray:
        self.tokenizer.enable_padding()
        encoded = self.tokenizer.encode_batch(texts)
        ids = np.array([e.ids for e in encoded], dtype=np.int64)
        mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)
        feed = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self.inputs:
            feed["token_type_ids"] = np.zeros_like(ids)
        hidden = self.session.run(None, feed)[0]
        weights = mask[..., None].astype(np.float32)
        return _normalise((hidden * weights).sum(axis=1) / weights.sum(axis=1).clip(1e-9))

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dims), dtype=np.float32)
        prefixed = [self.passage_prefix + t for t in texts]
        # Short texts first, so that one long passage does not pad a whole batch.
        order = sorted(range(len(prefixed)), key=lambda i: len(prefixed[i]))
        output = np.zeros((len(prefixed), self.dims), dtype=np.float32)
        for start in range(0, len(order), self.batch_size):
            batch = order[start : start + self.batch_size]
            output[batch] = self._encode([prefixed[i] for i in batch])
        return output

    def embed_query(self, text: str) -> np.ndarray:
        return self._encode([self.query_prefix + text])[0]


class CachedEmbedder:
    """Remembers passage vectors on disk by content hash, and query vectors in memory.

    Experiments re-chunk and re-rank the same text many times. CPU embedding is what makes
    that slow, so this keeps a sweep to minutes. The model name is part of the file name, and
    a changed model therefore never reuses old vectors.
    """

    def __init__(self, inner: Embedder, directory: str | Path):
        self.inner = inner
        self.name = inner.name
        self.dims = inner.dims
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", inner.name)
        self.path = Path(directory) / f"{safe}.sqlite"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.execute("create table if not exists v (key text primary key, vector blob)")
        self.queries: dict[str, np.ndarray] = {}

    @staticmethod
    def _key(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        keys = [self._key(t) for t in texts]
        found: dict[str, np.ndarray] = {}
        for start in range(0, len(keys), 500):
            part = keys[start : start + 500]
            marks = ",".join("?" * len(part))
            for key, blob in self.db.execute(
                f"select key, vector from v where key in ({marks})", part
            ):
                found[key] = np.frombuffer(blob, dtype=np.float32)
        missing = list({k: t for k, t in zip(keys, texts, strict=True) if k not in found}.items())
        if missing:
            vectors = self.inner.embed_passages([text for _, text in missing])
            rows = []
            for (key, _), vector in zip(missing, vectors, strict=True):
                found[key] = np.asarray(vector, dtype=np.float32)
                rows.append((key, found[key].tobytes()))
            self.db.executemany("insert or replace into v values (?, ?)", rows)
            self.db.commit()
        if not keys:
            return np.zeros((0, self.dims), dtype=np.float32)
        return np.stack([found[key] for key in keys])

    def embed_query(self, text: str) -> np.ndarray:
        if text not in self.queries:
            self.queries[text] = self.inner.embed_query(text)
        return self.queries[text]


def get_embedder(spec: str, cache_dir: str | Path | None = None) -> Embedder:
    embedder = _build_embedder(spec)
    return CachedEmbedder(embedder, cache_dir) if cache_dir else embedder


def _build_embedder(spec: str) -> Embedder:
    kind, _, arg = spec.partition(":")
    if kind == "onnx":
        return OnnxEmbedder(arg or "data/models/multilingual-e5-small")
    if kind == "hash":
        return HashingEmbedder(int(arg) if arg else 512)
    if kind == "spacy":
        return SpacyEmbedder(arg or "nl_core_news_md")
    if kind == "st":
        return SentenceTransformerEmbedder(arg) if arg else SentenceTransformerEmbedder()
    raise ValueError(
        f"unknown embedder {spec!r}: use st:<model>, onnx:<dir>, spacy:<model> or hash[:dims]"
    )
