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
    "court", "date", "doc_type", "subjects", "url", "acl", "refs",
]  # fmt: skip


def analysis_settings(compound_words: list[str]) -> dict:
    """The built-in `dutch` analyzer rebuilt by hand, plus Lucene's dictionary decompounder.

    The decompounder runs before stemming, because its word list holds unstemmed words.
    """
    return {
        "analysis": {
            "filter": {
                "dutch_stop": {"type": "stop", "stopwords": "_dutch_"},
                "dutch_stemmer": {"type": "stemmer", "language": "dutch"},
                "dutch_compounds": {
                    "type": "dictionary_decompounder",
                    "word_list": compound_words,
                    "min_word_size": 9,
                    "min_subword_size": 4,
                    "only_longest_match": True,
                },
            },
            "analyzer": {
                "dutch_compound": {
                    "tokenizer": "standard",
                    "filter": ["lowercase", "dutch_stop", "dutch_compounds", "dutch_stemmer"],
                }
            },
        }
    }


def index_body(dims: int, compound_words: list[str] | None = None) -> dict:
    analyzer = "dutch_compound" if compound_words else "dutch"
    settings: dict = {"number_of_shards": 1, "number_of_replicas": 0}
    if compound_words:
        settings |= analysis_settings(compound_words)
    return {
        "settings": settings,
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
                    "analyzer": analyzer,
                    "fields": {"plain": {"type": "text", "analyzer": "standard"}},
                },
                "title": {"type": "text", "analyzer": "dutch"},
                "court": {"type": "keyword"},
                "date": {"type": "date", "format": "strict_date"},
                "doc_type": {"type": "keyword"},
                "subjects": {"type": "keyword"},
                "acl": {"type": "keyword"},
                "refs": {"type": "keyword"},
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
    if filters.groups is not None:
        # An empty `terms` list matches nothing, which is the safe outcome for no groups.
        clauses.append({"terms": {"acl": sorted(filters.groups)}})
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
    def __init__(
        self, client: Elasticsearch, index: str, compound_words: list[str] | None = None
    ):
        self.client = client
        self.index = index
        self.compound_words = compound_words

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
            self.client.indices.create(
                index=self.index, **index_body(dims, self.compound_words)
            )

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

    def by_refs(self, refs: list[str], k: int, filters: Filters | None = None) -> list[Hit]:
        """First chunk of each document citing a ref, with most matching refs first."""
        wanted = [{"constant_score": {"filter": {"term": {"refs": ref}}}} for ref in refs]
        response = self.client.search(
            index=self.index,
            query={
                "bool": {
                    "should": wanted,
                    "minimum_should_match": 1,
                    "filter": [{"term": {"position": 0}}, *filter_clauses(filters)],
                }
            },
            size=k,
            source_includes=SOURCE_FIELDS,
        )
        return [self._hit(raw) for raw in response["hits"]["hits"]]

    def term_coverage(self, query: str) -> float:
        """Share of the query's terms that occur in the index, after Dutch analysis."""
        analyzed = self.client.indices.analyze(index=self.index, field="text", text=query)
        terms = list(dict.fromkeys(token["token"] for token in analyzed["tokens"]))
        if not terms:
            return 0.0
        found = sum(
            1 for term in terms
            if self.client.count(index=self.index, query={"term": {"text": term}})["count"]
        )  # fmt: skip
        return found / len(terms)

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
    if key in ("subjects", "acl", "refs"):
        return []
    if key == "position":
        return 0
    return ""
