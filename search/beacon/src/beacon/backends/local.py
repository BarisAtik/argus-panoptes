"""In-process BM25 and exact cosine search, for demos, CI and small corpora.

It keeps everything in memory and rebuilds on every start. Results are close to
Elasticsearch but not identical: the analyzers differ slightly and kNN here is exact.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict

import numpy as np

from ..compounds import Decompounder
from ..models import Chunk, Filters, Hit
from ..text import tokens


class LocalBackend:
    def __init__(
        self, k1: float = 1.2, b: float = 0.75, decompounder: Decompounder | None = None
    ):
        self.k1 = k1
        self.b = b
        self.decompounder = decompounder
        self.chunks: list[Chunk] = []
        self.vectors: np.ndarray | None = None
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        self.lengths: list[int] = []

    def create(self, dims: int, recreate: bool = False) -> None:
        self.__init__(self.k1, self.b, self.decompounder)
        self.vectors = np.zeros((0, dims), dtype=np.float32)

    def add(self, chunks: list[Chunk], vectors: np.ndarray) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors differ in length")
        if self.vectors is None:
            self.create(vectors.shape[1])
        for chunk in chunks:
            index = len(self.chunks)
            self.chunks.append(chunk)
            terms = Counter(tokens(chunk.text, self.decompounder))
            self.lengths.append(sum(terms.values()))
            for term, frequency in terms.items():
                self.postings[term].append((index, frequency))
        self.vectors = np.vstack([self.vectors, vectors.astype(np.float32)])

    def _allowed(self, filters: Filters | None) -> set[int] | None:
        if filters is None:
            return None
        return {i for i, chunk in enumerate(self.chunks) if filters.matches(chunk)}

    def lexical(self, query: str, k: int, filters: Filters | None = None) -> list[Hit]:
        if not self.chunks:
            return []
        allowed = self._allowed(filters)
        total = len(self.chunks)
        average = sum(self.lengths) / total or 1.0
        scores: dict[int, float] = defaultdict(float)
        for term in set(tokens(query, self.decompounder)):
            postings = self.postings.get(term, [])
            if not postings:
                continue
            frequency_docs = len(postings)
            idf = math.log(1 + (total - frequency_docs + 0.5) / (frequency_docs + 0.5))
            for index, frequency in postings:
                if allowed is not None and index not in allowed:
                    continue
                norm = 1 - self.b + self.b * self.lengths[index] / average
                scores[index] += idf * frequency * (self.k1 + 1) / (frequency + self.k1 * norm)
        best = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:k]
        return [Hit(self.chunks[index], score) for index, score in best]

    def dense(self, vector: np.ndarray, k: int, filters: Filters | None = None) -> list[Hit]:
        if not self.chunks:
            return []
        similarity = self.vectors @ vector
        order = np.argsort(-similarity, kind="stable")
        allowed = self._allowed(filters)
        hits: list[Hit] = []
        for index in order:
            if allowed is not None and int(index) not in allowed:
                continue
            hits.append(Hit(self.chunks[int(index)], float(similarity[index])))
            if len(hits) == k:
                break
        return hits

    def by_refs(self, refs: list[str], k: int, filters: Filters | None = None) -> list[Hit]:
        """First chunk of each document citing a ref, with most matching refs first."""
        wanted = set(refs)
        scored = [
            (len(wanted.intersection(chunk.refs)), index)
            for index, chunk in enumerate(self.chunks)
            if chunk.position == 0 and (filters is None or filters.matches(chunk))
        ]
        best = sorted((item for item in scored if item[0]), key=lambda i: (-i[0], i[1]))[:k]
        return [Hit(self.chunks[index], float(score)) for score, index in best]

    def term_coverage(self, query: str) -> float:
        """Share of the query's terms that occur anywhere in the index."""
        terms = set(tokens(query, self.decompounder))
        if not terms:
            return 0.0
        return sum(1 for term in terms if term in self.postings) / len(terms)

    def document_chunks(self, doc_id: str) -> list[Chunk]:
        return sorted(
            (chunk for chunk in self.chunks if chunk.doc_id == doc_id),
            key=lambda chunk: chunk.position,
        )

    def delete_document(self, doc_id: str) -> None:
        """Rebuilds the index, which is fine at the small scale this backend is for."""
        keep = [i for i, chunk in enumerate(self.chunks) if chunk.doc_id != doc_id]
        chunks = [self.chunks[i] for i in keep]
        vectors = self.vectors[keep]
        self.create(vectors.shape[1])
        if chunks:
            self.add(chunks, vectors)

    def stats(self) -> dict:
        return {
            "backend": "local",
            "chunks": len(self.chunks),
            "documents": len({chunk.doc_id for chunk in self.chunks}),
        }
