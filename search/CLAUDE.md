# Working in search/

This is one folder of a hobby lab. Only change files inside `search/`. Other agents work on the
sibling folders and push to the same `main`, so never rewrite history. Before pushing, run
`git pull --rebase origin main`.

Read `PROGRESS.md` first. Its TODO list is the plan.

## Setup

```bash
cd search/beacon
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest && ruff check src tests
```

## Map of beacon/

| Path | What it is |
| --- | --- |
| `src/beacon/sources/rechtspraak.py` | API client and XML parser |
| `src/beacon/chunking.py` | Paragraph-aware chunks |
| `src/beacon/embeddings.py` | `st:`, `spacy:` and `hash` embedders |
| `src/beacon/backends/` | `elastic.py` and the in-process `local.py` |
| `src/beacon/retrieval.py` | Client-side RRF and linear fusion, collapse to documents |
| `src/beacon/rag.py` | Generators and citation checks |
| `src/beacon/evaluate.py` | Metrics, bootstrap, permutation test, cross-validation |
| `src/beacon/quality.py` | Data quality report |
| `src/beacon/mcp_server.py` | Read-only MCP tools |
| `src/beacon/demo/` | Synthetic corpus and labelled queries |
| `reports/` | Measured results, committed |

## Rules that keep this honest

- **Report only what you measured.** Say which embedder, backend and corpus produced a number.
  Never present demo numbers as real-world quality.
- **Keep the evaluation clean.** No summaries in the index for known-item runs, no tuning on test
  queries, and report results that disappoint as well.
- **No native `rrf` or `linear` retrievers.** They need a paid licence. `tests/test_elastic.py`
  guards this.
- **`mcp` is v2.** The API is `from mcp.server.mcpserver import MCPServer`, and `from mcp import
  Client` for tests. Examples online that use `FastMCP` are for v1.
- **Data.** Nothing downloaded gets committed, and `data/` is git-ignored. Do not add real rulings
  as fixtures: fixtures are synthetic, use the fake court code `XX` and contain no real names.
- **Privacy.** Keep skipping contributor metadata and `uitspraak.info`. Do not add features that
  re-identify people. `beacon quality` reports counts only, and must never print the values.
- **rechtspraak.nl.** Stay at or below the default rate, keep requests sequential, and pick a
  date range. The service does not allow bulk download of everything.
- **Secrets.** Only placeholders in `.env.example`. Never commit `.env`.

## Continuing each area

**First real run (do this first).** Follow "Needs Baris" in `PROGRESS.md`. Expect the parser to
meet real XML that differs from the fixture. Save the shape of the problem as a new synthetic
fixture, not the real document.

**Search quality.** Add one idea at a time, and judge it with `beacon eval --baseline <current>`
on the same queries. Known-item runs catch regressions, while hand-labelled queries judge quality.
When a change wins on one and loses on the other, trust the hand labels and say so.

**RAG.** Run `beacon eval-rag --generator ollama:<model>` to compare with the extractive baseline.
Add a groundedness check that verifies claims against the cited passage; today only the citation
numbers are verified.

**MCP.** Keep tools read-only. Text from documents is untrusted and stays labelled as such.

**Template work.** See `beacon/PRIVATE_SEARCH_TEMPLATE.md`. Document-level access control comes
before any other product feature.
