"""Request shapes, with a stub client. See test_integration.py for a real server."""

import json

import numpy as np

from beacon.backends.elastic import (
    ElasticBackend,
    filter_clauses,
    index_body,
    knn_clause,
    lexical_query,
)
from beacon.models import Filters


class StubClient:
    def __init__(self):
        self.calls = []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "hits": {
                "hits": [
                    {
                        "_score": 2.5,
                        "_source": {"id": "a#0", "doc_id": "a", "text": "tekst"},
                        "highlight": {"text": ["<em>tekst</em>"]},
                    }
                ]
            }
        }


def test_mapping_uses_dutch_analysis_and_filterable_keywords():
    properties = index_body(384)["mappings"]["properties"]
    assert properties["text"]["analyzer"] == "dutch"
    assert properties["court"]["type"] == "keyword"
    assert properties["embedding"]["dims"] == 384
    assert properties["embedding"]["similarity"] == "cosine"
    assert properties["embedding"]["index_options"] == {"type": "int8_hnsw"}


def test_vectors_stay_out_of_source():
    assert index_body(8)["mappings"]["_source"] == {"excludes": ["embedding"]}


def test_filters_translate_to_clauses():
    clauses = filter_clauses(
        Filters(court="R", subject="S", doc_type="T", date_from="2024-01-01", date_to="2024-12-31")
    )
    assert {"term": {"court": "R"}} in clauses
    assert {"term": {"subjects": "S"}} in clauses
    assert {"range": {"date": {"gte": "2024-01-01", "lte": "2024-12-31"}}} in clauses
    assert filter_clauses(None) == []


def test_filters_go_in_filter_context():
    query = lexical_query("huur", Filters(court="R"))
    assert query["bool"]["filter"] == [{"term": {"court": "R"}}]


def test_knn_uses_filter_and_enough_candidates():
    clause = knn_clause(np.array([0.5, 0.5]), 200, Filters(court="R"))
    assert clause["num_candidates"] == 800
    assert clause["filter"] == [{"term": {"court": "R"}}]
    assert "filter" not in knn_clause(np.zeros(2), 5, None)


def test_results_become_hits():
    client = StubClient()
    hits = ElasticBackend(client, "idx").lexical("huur", 3)
    assert hits[0].chunk.doc_id == "a"
    assert hits[0].chunk.subjects == []
    assert hits[0].score == 2.5
    assert hits[0].highlight == "<em>tekst</em>"


def test_no_request_needs_a_paid_licence():
    client = StubClient()
    backend = ElasticBackend(client, "idx")
    backend.lexical("huur", 3, Filters(court="R"))
    backend.dense(np.zeros(4), 3)
    payload = json.dumps(client.calls)
    assert '"rrf"' not in payload
    assert '"linear"' not in payload
    assert "retriever" not in payload
