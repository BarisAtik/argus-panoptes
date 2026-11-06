# 🔦 The Watchtower — search

Elasticsearch experiments: making large piles of data searchable, and measuring whether it worked.

Each experiment has its own folder. See [`PROGRESS.md`](PROGRESS.md) for where things stand and
[`CLAUDE.md`](CLAUDE.md) for how to carry on with Claude Code.

| Experiment | What it does | Dataset | Status |
| --- | --- | --- | --- |
| [`beacon/`](beacon/) | Hybrid search with query routing, RAG with claim checks, a small web app with per-user access, folder ingest, prompt-injection tests, retrieval evaluation and an MCP server on single-node Elasticsearch | Dutch government guidance (Algoritmekader, Logius standards) and court decisions (rechtspraak.nl), downloaded at run time; synthetic demo set included | Three one-shot evaluations on real Dutch text. Web app and MCP over HTTP tested in a browser. First run on real Elasticsearch still to do |

## Quick start

```bash
cd beacon
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
make demo
make real-data    # real Dutch text and labels, no Docker
pip install -e ".[web,onnx,files,compounds]"    # then see beacon/PRIVATE_SEARCH_TEMPLATE.md
```

## Ideas on the list

- A cross-encoder reranker, measured against plain hybrid
- OCR for scanned PDFs, so the ingest report has less to complain about
- Claim checking with a real entailment model, since 42% of subtle errors get past the rules
- Search over other Dutch open data
