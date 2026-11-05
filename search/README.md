# 🔦 The Watchtower — search

Elasticsearch experiments: making large piles of data searchable, and measuring whether it worked.

Each experiment has its own folder. See [`PROGRESS.md`](PROGRESS.md) for where things stand and
[`CLAUDE.md`](CLAUDE.md) for how to carry on with Claude Code.

| Experiment | What it does | Dataset | Status |
| --- | --- | --- | --- |
| [`beacon/`](beacon/) | Hybrid search, RAG with checked citations, retrieval evaluation and an MCP server on single-node Elasticsearch | Dutch court decisions from rechtspraak.nl, downloaded at run time; synthetic demo set included | Works end to end on the demo set; first run on real data and real Elasticsearch still to do |

## Quick start

```bash
cd beacon
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
make demo
```

## Ideas on the list

- Dutch compound splitting for BM25
- A cross-encoder reranker, measured against plain hybrid
- A/B of chunk sizes on known-item queries
- Search over other Dutch open data
