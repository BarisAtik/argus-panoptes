"""Hybrid retrieval: run lexical and dense search, fuse in the client, collapse to documents.

Fusion happens here and not in Elasticsearch because the native rrf and linear retrievers
are Enterprise features. It also means both engines share one tested implementation.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace

from .backends import Backend
from .citations import article_refs, extract_refs
from .embeddings import Embedder
from .models import Chunk, Filters, Hit
from .routing import lexical_weight
from .synonyms import expand

MODES = ("bm25", "dense", "rrf", "linear", "smart")
ECLI = re.compile(r"\bECLI:[A-Z]{2}:[A-Z0-9]{1,7}:\d{4}:[A-Z0-9.]{1,25}\b", re.IGNORECASE)


def rrf_fuse(
    rankings: Sequence[Sequence[Hit]],
    rrf_k: int = 60,
    weights: Sequence[float] | None = None,
) -> list[Hit]:
    """Reciprocal rank fusion. Uses ranks only, so score scales do not matter."""
    weights = weights or [1.0] * len(rankings)
    if len(weights) != len(rankings):
        raise ValueError("one weight per ranking")
    scores: dict[str, float] = {}
    hits: dict[str, Hit] = {}
    for ranking, weight in zip(rankings, weights, strict=True):
        if weight <= 0:
            continue
        for rank, hit in enumerate(ranking, start=1):
            scores[hit.chunk.id] = scores.get(hit.chunk.id, 0.0) + weight / (rrf_k + rank)
            # Keep the version that carries a highlight.
            if hit.chunk.id not in hits or (hit.highlight and not hits[hit.chunk.id].highlight):
                hits[hit.chunk.id] = hit
    order = sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))
    return [Hit(hits[c].chunk, scores[c], hits[c].highlight) for c in order]


def _min_max(ranking: Sequence[Hit]) -> dict[str, float]:
    if not ranking:
        return {}
    values = [hit.score for hit in ranking]
    low, high = min(values), max(values)
    if high == low:
        return {hit.chunk.id: 1.0 for hit in ranking}
    return {hit.chunk.id: (hit.score - low) / (high - low) for hit in ranking}


def linear_fuse(lexical: Sequence[Hit], dense: Sequence[Hit], alpha: float = 0.5) -> list[Hit]:
    """Weighted sum of min-max scores. alpha=1 is all lexical, alpha=0 is all dense."""
    if not 0.0 <= alpha <= 1.0:
        raise ValueError("alpha must be between 0 and 1")
    lexical_scores = _min_max(lexical)
    dense_scores = _min_max(dense)
    hits = {hit.chunk.id: hit for hit in dense}
    hits.update({hit.chunk.id: hit for hit in lexical})
    scores = {
        chunk_id: alpha * lexical_scores.get(chunk_id, 0.0)
        + (1 - alpha) * dense_scores.get(chunk_id, 0.0)
        for chunk_id in hits
    }
    order = sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))
    return [Hit(hits[c].chunk, scores[c], hits[c].highlight) for c in order]


def collapse(hits: Sequence[Hit], k: int) -> list[Hit]:
    """Keep the best chunk per document, so one long ruling cannot fill the result list."""
    seen: set[str] = set()
    result: list[Hit] = []
    for hit in hits:
        if hit.chunk.doc_id not in seen:
            seen.add(hit.chunk.doc_id)
            result.append(hit)
            if len(result) == k:
                break
    return result


@dataclass
class Retriever:
    backend: Backend
    embedder: Embedder
    candidates: int = 100
    rrf_k: int = 60
    alpha: float = 0.5
    # When set, every path below is limited to documents these groups may read. It lives here
    # and not in a tool argument, so that an agent cannot widen its own access.
    groups: frozenset[str] | None = None
    # Only used by mode "smart". The CLI turns all of them on, see reports/ak-routing.md.
    routing: str = "none"
    routing_power: float = 1.0
    synonyms: bool = False
    refs: bool = False

    def _scoped(self, filters: Filters | None) -> Filters | None:
        if self.groups is None:
            return filters
        return replace(filters or Filters(), groups=self.groups)

    def chunks(
        self, query: str, mode: str = "rrf", filters: Filters | None = None
    ) -> list[Hit]:
        """Ranked chunks for a query, before collapsing to documents."""
        if mode not in MODES:
            raise ValueError(f"unknown mode {mode!r}; expected one of {MODES}")
        if not query.strip():
            return []
        filters = self._scoped(filters)
        if mode == "smart":
            return self._smart(query, filters)
        lexical: list[Hit] = []
        dense: list[Hit] = []
        if mode != "dense":
            lexical = self.backend.lexical(query, self.candidates, filters)
        if mode != "bm25":
            vector = self.embedder.embed_query(query)
            dense = self.backend.dense(vector, self.candidates, filters)
        if mode == "bm25":
            return lexical
        if mode == "dense":
            return dense
        if mode == "rrf":
            return rrf_fuse([lexical, dense], self.rrf_k)
        return linear_fuse(lexical, dense, self.alpha)

    def _smart(self, query: str, filters: Filters | None) -> list[Hit]:
        """RRF that adapts to the query: routing, synonyms and exact citations. Each is optional."""
        weight = lexical_weight(
            query, self.routing, self.backend.term_coverage, self.routing_power
        )
        vector = self.embedder.embed_query(query)
        rankings = [self.backend.dense(vector, self.candidates, filters)]
        weights = [1.0]
        if weight > 0:
            text = expand(query) if self.synonyms else query
            rankings.append(self.backend.lexical(text, self.candidates, filters))
            weights.append(weight)
        cited = article_refs(extract_refs(query)) if self.refs else []
        if cited:
            rankings.append(self.backend.by_refs(cited, self.candidates, filters))
            weights.append(1.0)
        return rrf_fuse(rankings, self.rrf_k, weights)

    def search(
        self, query: str, mode: str = "rrf", k: int = 10, filters: Filters | None = None
    ) -> list[Hit]:
        """Best documents for a query. An ECLI in the query is resolved by exact lookup first."""
        exact = self._exact(query, filters)
        if exact:
            return exact[:k]
        return collapse(self.chunks(query, mode, filters), k)

    def _exact(self, query: str, filters: Filters | None) -> list[Hit]:
        filters = self._scoped(filters)
        hits: list[Hit] = []
        for match in ECLI.findall(query):
            chunks = self.backend.document_chunks(match.upper())
            if chunks and (filters is None or filters.matches(chunks[0])):
                hits.append(Hit(chunks[0], 1.0))
        return hits

    def document(self, doc_id: str) -> list[Chunk]:
        """All chunks of a document. A forbidden document looks exactly like a missing one."""
        chunks = self.backend.document_chunks(doc_id)
        scope = self._scoped(None)
        return [chunk for chunk in chunks if scope is None or scope.matches(chunk)]
