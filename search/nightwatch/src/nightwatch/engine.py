"""A small REST client for Elasticsearch and OpenSearch.

It uses only `_bulk`, `_count`, `_search` and index creation, which both engines share, so it
needs no vendor client and no product check. Mapping variants are the point of the project: the
same rule on the same log can give a different answer depending on how the fields were mapped.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

import httpx

IGNORE_ABOVE_SAFE = 8191  # the largest value that cannot pass Lucene's 32766-byte term limit
IGNORE_ABOVE_SHIPPER = 1024  # the default in common log-shipper templates
CHUNK_CHARS = 8000
CHUNK_OVERLAP = 1024

META = {
    "case_id": {"type": "keyword"},
    "dataset_id": {"type": "keyword"},
    "split": {"type": "keyword"},
}
LOWER = {"analysis": {"normalizer": {"lower": {"type": "custom", "filter": ["lowercase"]}}}}


def _template(mapping: dict) -> dict:
    return {
        "dynamic_templates": [{"strings": {"match_mapping_type": "string", "mapping": mapping}}],
        "properties": META,
    }


# name -> index body
VARIANTS: dict[str, dict[str, Any]] = {
    # What you get by indexing JSON with no template: text, plus a .keyword sub-field.
    "dynamic_text": {"mappings": {"properties": META}},
    "keyword_raw": {
        "mappings": _template({"type": "keyword", "ignore_above": IGNORE_ABOVE_SAFE}),
    },
    "keyword_lower": {
        "settings": LOWER,
        "mappings": _template(
            {"type": "keyword", "normalizer": "lower", "ignore_above": IGNORE_ABOVE_SAFE}
        ),
    },
    "keyword_lower_1024": {
        "settings": LOWER,
        "mappings": _template(
            {"type": "keyword", "normalizer": "lower", "ignore_above": IGNORE_ABOVE_SHIPPER}
        ),
    },
    "wildcard_raw": {"mappings": _template({"type": "wildcard"})},
    "wildcard_lower": {
        "settings": LOWER,
        "mappings": _template({"type": "wildcard", "normalizer": "lower"}),
    },
}


# Same mapping, different ingest: see `chunk_long_values`. `tuned` also rewrites regexes.
VARIANTS["keyword_lower_chunked"] = VARIANTS["keyword_lower"]
VARIANTS["tuned"] = VARIANTS["keyword_lower"]
CHUNKED = {"keyword_lower_chunked", "tuned"}


def chunk_long_values(event: dict[str, str]) -> dict:
    """Store long values as overlapping pieces of a multi-valued keyword.

    `ignore_above` drops a long value from the index without a word, and a long PowerShell script
    is the kind of value a detection needs. A pattern up to CHUNK_OVERLAP long is always whole in
    one piece. A lower bound on recall, not exactness: a suffix test can match a piece's end.
    """
    out: dict = {}
    step = CHUNK_CHARS - CHUNK_OVERLAP
    for key, value in event.items():
        if len(value) > IGNORE_ABOVE_SAFE:
            out[key] = [value[i : i + CHUNK_CHARS] for i in range(0, len(value), step)]
        else:
            out[key] = value
    return out


@dataclass
class Engine:
    url: str
    user: str | None = None
    password: str | None = None
    timeout: float = 60.0

    def __post_init__(self) -> None:
        auth = (self.user, self.password) if self.user and self.password else None
        self.client = httpx.Client(base_url=self.url, auth=auth, timeout=self.timeout)

    def info(self) -> dict[str, Any]:
        return self.client.get("/").raise_for_status().json()

    def create(self, index: str, variant: str) -> None:
        self.client.delete(f"/{index}")
        body = json.loads(json.dumps(VARIANTS[variant]))
        settings = body.setdefault("settings", {})
        settings.update(
            number_of_shards=1,
            number_of_replicas=0,
            refresh_interval="-1",
        )
        settings["index.mapping.total_fields.limit"] = 5000
        settings["index.max_regex_length"] = 8000
        self.client.put(f"/{index}", json=body).raise_for_status()

    def bulk(self, index: str, events: Iterable[dict], batch: int = 2000) -> dict[str, int]:
        """Returns counts of indexed and rejected events. Rejections must be reported."""
        stats = {"indexed": 0, "rejected": 0}

        def send(lines: list[str]) -> None:
            response = self.client.post(
                f"/{index}/_bulk",
                content="\n".join(lines) + "\n",
                headers={"content-type": "application/x-ndjson"},
            )
            response.raise_for_status()
            for item in response.json()["items"]:
                if item["index"].get("error"):
                    stats["rejected"] += 1
                else:
                    stats["indexed"] += 1

        lines: list[str] = []
        for event in events:
            lines += ['{"index":{}}', json.dumps(event, ensure_ascii=False)]
            if len(lines) >= 2 * batch:
                send(lines)
                lines = []
        if lines:
            send(lines)
        self.client.post(f"/{index}/_refresh").raise_for_status()
        self.client.put(f"/{index}/_settings", json={"refresh_interval": "1s"})
        return stats

    def _body(self, query: str, within: dict | None) -> dict:
        string = {"query_string": {"query": query, "analyze_wildcard": False}}
        return {"bool": {"must": [string], "filter": [within] if within else []}}

    def count(self, index: str, query: str, within: dict | None = None) -> int:
        """Raises `QueryFailed` when the engine refuses the query, so 0 always means 0."""
        response = self.client.post(
            f"/{index}/_count", json={"query": self._body(query, within)}
        )
        if response.status_code != 200:
            raise QueryFailed(_reason(response))
        return response.json()["count"]

    def counts_by(self, index: str, query: str, field: str, size: int = 2000) -> dict[str, int]:
        body = {
            "size": 0,
            "query": self._body(query, None),
            "aggs": {"by": {"terms": {"field": field, "size": size}}},
        }
        response = self.client.post(f"/{index}/_search", json=body)
        if response.status_code != 200:
            raise QueryFailed(_reason(response))
        buckets = response.json()["aggregations"]["by"]["buckets"]
        return {bucket["key"]: bucket["doc_count"] for bucket in buckets}

    def search(self, index: str, query: str, size: int = 10) -> list[dict[str, Any]]:
        body = {"size": size, "query": self._body(query, None)}
        response = self.client.post(f"/{index}/_search", json=body)
        if response.status_code != 200:
            raise QueryFailed(_reason(response))
        return [hit["_source"] for hit in response.json()["hits"]["hits"]]


class QueryFailed(RuntimeError):
    pass


def _reason(response: httpx.Response) -> str:
    try:
        error = response.json()["error"]
        cause = (error.get("root_cause") or [error])[0]
        return f"{cause.get('type')}: {str(cause.get('reason'))[:200]}"
    except (ValueError, KeyError, TypeError, AttributeError):
        return f"HTTP {response.status_code}"


def read_jsonl(path) -> Iterator[dict]:
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            yield json.loads(line)
