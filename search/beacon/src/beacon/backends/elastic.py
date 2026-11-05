"""Elasticsearch backend. Stays within what the free Basic licence allows.

The native `rrf` and `linear` retrievers need an Enterprise licence and fail with a
403 security_exception on Basic, so this class only runs plain BM25 and plain kNN.
"""

from __future__ import annotations

import numpy as np
from elasticsearch import Elasticsearch, NotFoundError
from elasticsearch.helpers import bulk

from ..config import Settings
from ..models import Chunk, Filters, Hit

SOURCE_FIELDS = [
    "id", "doc_id", "position", "section", "text", "title",
    "court", "date", "doc_type", "subjects", "url",
]  # fmt: skip


def index_body(dims: int) -> dict:
    return {
        "settings": {"number_of_shards": 1, "number_of_replicas": 0},
        "mappings": {
            "dynamic": "strict",
            # Vectors stay out of _source: they would double the disk use, and the corpus
            # file remains the source of truth for a rebuild.
            "_source": {"excludes": ["embedding"]},
            "properties": {
                "id": {"type": "keyword"},
                "doc_id": {"type": "keyword"},
                "position": {"type": "integer"},
                "section": {"type": "keyword"},
                "text": {
                    "type": "text",
                    "analyzer": "dutch",
                    "fields": {"plain": {"type": "text", "analyzer": "standard"}},
                },
                "title": {"type": "text", "analyzer": "dutch"},
                "court": {"type": "keyword"},
                "date": {"type": "date", "format": "strict_date"},
                "doc_type": {"type": "keyword"},
                "subjects": {"type": "keyword"},
                "url": {"type": "keyword", "index": False},
                "embedding": {
                    "type": "dense_vector",
                    "dims": dims,
                    "index": True,
                    "similarity": "cosine",
                    # Explicit, because the default for dims >= 384 is BBQ quantisation,
                    # which would make results depend on the server version.
                    "index_options": {"type": "int8_hnsw"},
                },
            },
        },
    }


def filter_clauses(filters: Filters | None) -> list[dict]:
    if filters is None:
        return []
    clauses: list[dict] = []
    if filters.court:
        clauses.append({"term": {"court": filters.court}})
    if filters.subject:
        clauses.append({"term": {"subjects": filters.subject}})
    if filters.doc_type:
        clauses.append({"term": {"doc_type": filters.doc_type}})
    if filters.date_from or filters.date_to:
        bounds = {}
        if filters.date_from:
            bounds["gte"] = filters.date_from
        if filters.date_to:
            bounds["lte"] = filters.date_to
        clauses.append({"range": {"date": bounds}})
    return clauses


def lexical_query(query: str, filters: Filters | None) -> dict:
    return {
        "bool": {
            "must": [{"match": {"text": {"query": query}}}],
            "filter": filter_clauses(filters),
        }
    }


def knn_clause(vector: np.ndarray, k: int, filters: Filters | None) -> dict:
    clause: dict = {
        "field": "embedding",
        "query_vector": [float(x) for x in vector],
        "k": k,
        "num_candidates": max(100, 4 * k),
    }
    filter_ = filter_clauses(filters)
    if filter_:
        clause["filter"] = filter_
    return clause


class ElasticBackend:
    def __init__(self, client: Elasticsearch, index: str):
        self.client = client
        self.index = index

    @classmethod
    def from_settings(cls, settings: Settings) -> ElasticBackend:
        auth = (settings.es_user, settings.es_password) if settings.es_password else None
        return cls(Elasticsearch(settings.es_url, basic_auth=auth), settings.index)

    def create(self, dims: int, recreate: bool = False) -> None:
        exists = bool(self.client.indices.exists(index=self.index))
        if exists and recreate:
            self.client.indices.delete(index=self.index)
            exists = False
        if not exists:
            self.client.indices.create(index=self.index, **index_body(dims))

    def add(self, chunks: list[Chunk], vectors: np.ndarray) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors differ in length")
        actions = (
            {
                "_index": self.index,
                "_id": chunk.id,
                "_source": {
                    **{k: v for k, v in chunk.source().items() if v != ""},
                    "embedding": [float(x) for x in vector],
                },
            }
            for chunk, vector in zip(chunks, vectors, strict=True)
        )
        bulk(self.client.options(request_timeout=120), actions, chunk_size=200)
        self.client.indices.refresh(index=self.index)

    @staticmethod
    def _hit(raw: dict) -> Hit:
        source = raw["_source"]
        chunk = Chunk(**{key: source.get(key, _default(key)) for key in SOURCE_FIELDS})
        fragments = raw.get("highlight", {}).get("text", [])
        return Hit(chunk, float(raw["_score"]), " … ".join(fragments))

    def lexical(self, query: str, k: int, filters: Filters | None = None) -> list[Hit]:
        response = self.client.search(
            index=self.index,
            query=lexical_query(query, filters),
            size=k,
            source_includes=SOURCE_FIELDS,
            highlight={"fields": {"text": {"fragment_size": 180, "number_of_fragments": 2}}},
        )
        return [self._hit(raw) for raw in response["hits"]["hits"]]

    def dense(self, vector: np.ndarray, k: int, filters: Filters | None = None) -> list[Hit]:
        response = self.client.search(
            index=self.index,
            knn=knn_clause(vector, k, filters),
            size=k,
            source_includes=SOURCE_FIELDS,
        )
        return [self._hit(raw) for raw in response["hits"]["hits"]]

    def document_chunks(self, doc_id: str) -> list[Chunk]:
        response = self.client.search(
            index=self.index,
            query={"term": {"doc_id": doc_id}},
            sort=[{"position": "asc"}],
            size=1000,
            source_includes=SOURCE_FIELDS,
        )
        return [self._hit({**raw, "_score": 0.0}).chunk for raw in response["hits"]["hits"]]

    def stats(self) -> dict:
        try:
            chunks = int(self.client.count(index=self.index)["count"])
            result = self.client.search(
                index=self.index,
                size=0,
                aggs={"documents": {"cardinality": {"field": "doc_id"}}},
            )
            documents = int(result["aggregations"]["documents"]["value"])
        except NotFoundError:
            chunks = documents = 0
        return {"backend": "elastic", "index": self.index, "chunks": chunks, "documents": documents}


def _default(key: str):
    if key == "subjects":
        return []
    if key == "position":
        return 0
    return ""
