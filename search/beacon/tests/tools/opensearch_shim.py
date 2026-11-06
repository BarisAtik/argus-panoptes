"""Run the Elasticsearch code path against OpenSearch, when Elasticsearch cannot be installed.

    python tests/tools/opensearch_shim.py --upstream http://localhost:9201 --port 9200
    BEACON_IT=1 ES_URL=http://localhost:9200 pytest -m integration

Some sandboxes can install OpenSearch but cannot reach Elastic's downloads. Both engines use
Lucene and nearly the same query language, so this still catches real mistakes in mappings,
analysis settings and filters. It is a stand-in for local testing and proves nothing about
Elasticsearch. Three things are faked here and stay untested:

* `dense_vector` and the `knn` search option. Vectors are stored as plain floats, and cosine
  similarity is computed in this process. There is no HNSW and no quantisation.
* The product header that the Elasticsearch client checks.
* Vendor media types, which are rewritten to plain JSON.
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import numpy as np


def plain_mapping(body: dict) -> dict:
    """Swap the vector field for something OpenSearch without its k-NN plugin accepts."""
    mappings = body.get("mappings", {})
    mappings.pop("_source", None)
    properties = mappings.get("properties", {})
    if "embedding" in properties:
        properties["embedding"] = {"type": "float", "index": False}
    return body


def knn_search(upstream: str, index: str, body: dict) -> dict:
    """Exact cosine search with the filter applied first, as Elasticsearch does."""
    knn = body["knn"]
    query = {"bool": {"filter": knn.get("filter", [])}}
    found = httpx.post(
        f"{upstream}/{index}/_search",
        json={"query": query, "size": 10_000, "_source": True},
        timeout=60,
    ).json()
    hits = found["hits"]["hits"]
    if not hits:
        return found
    vectors = np.array([hit["_source"]["embedding"] for hit in hits], dtype=np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True).clip(1e-9)
    target = np.array(knn["query_vector"], dtype=np.float32)
    target /= max(float(np.linalg.norm(target)), 1e-9)
    similarity = vectors @ target
    output = []
    for position in np.argsort(-similarity, kind="stable")[: knn["k"]]:
        hit = dict(hits[int(position)])
        hit["_score"] = float((1 + similarity[position]) / 2)
        hit["_source"] = {k: v for k, v in hit["_source"].items() if k != "embedding"}
        output.append(hit)
    found["hits"]["hits"] = output
    return found


def handler_for(upstream: str):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args) -> None:
            pass

        def _send(self, status: int, payload: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("X-Elastic-Product", "Elasticsearch")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)

        def _forward(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            path = self.path
            base = path.split("?")[0].strip("/")
            parts = base.split("/")
            if self.command == "GET" and base == "":
                info = {"version": {"number": "9.0.0", "build_flavor": "default"},
                        "tagline": "You Know, for Search"}  # fmt: skip
                self._send(200, json.dumps(info).encode())
                return
            if self.command == "PUT" and len(parts) == 1 and raw and base[0] != "_":
                raw = json.dumps(plain_mapping(json.loads(raw))).encode()
            if parts[-1] == "_search" and raw:
                body = json.loads(raw)
                if "knn" in body:
                    result = knn_search(upstream, parts[0], body)
                    self._send(200, json.dumps(result).encode())
                    return
            kind = "application/x-ndjson" if parts[-1] == "_bulk" else "application/json"
            response = httpx.request(
                self.command, upstream + path, content=raw,
                headers={"Content-Type": kind}, timeout=120,
            )  # fmt: skip
            self._send(response.status_code, response.content)

        do_GET = do_POST = do_PUT = do_DELETE = do_HEAD = _forward

    return Handler


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--upstream", default="http://localhost:9201")
    parser.add_argument("--port", type=int, default=9200)
    args = parser.parse_args()
    ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(args.upstream)).serve_forever()
