# 🔦 The Watchtower — search

Elasticsearch experiments: making large piles of data searchable, and measuring whether it worked.

Each experiment has its own folder. See [`PROGRESS.md`](PROGRESS.md) for where things stand and
[`CLAUDE.md`](CLAUDE.md) for how to carry on with Claude Code.

| Experiment | What it does | Dataset | Status |
| --- | --- | --- | --- |
| [`beacon/`](beacon/) | Hybrid search, RAG with checked citations, access control, prompt-injection tests, retrieval evaluation and an MCP server on single-node Elasticsearch | Dutch government guidance (Algoritmekader) and court decisions (rechtspraak.nl), downloaded at run time; synthetic demo set included | Scored on real Dutch text with independent labels and a one-shot holdout. First run on real Elasticsearch still to do |

## Quick start

```bash
cd beacon
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
make demo
make real-data    # real Dutch text and labels, no Docker
```

## Ideas on the list

- Route queries by language, because BM25 hurts English queries on Dutch text
- A cross-encoder reranker, measured against plain hybrid
- Keep statute references as a separate exact-match field
- Search over other Dutch open data
