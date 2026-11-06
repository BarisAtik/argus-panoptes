# Working in search/

This is one folder of a hobby lab. Only change files inside `search/`. Other agents work on the
sibling folders and push to the same `main`, so never rewrite history. Before pushing, run
`git pull --rebase origin main`.

Read `PROGRESS.md` first. Its TODO list is the plan.

**Work autonomously.** Do not stop to ask questions: make a sensible choice, note it in
`PROGRESS.md`, and carry on. The only exceptions are steps that need Baris's own accounts, money
or competition submissions. List those under "Needs Baris" and move on to the next item.

## Setup

```bash
cd search/beacon
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,onnx,compounds,files,web]"
pytest && ruff check src tests evals
make real-data   # corpus, labels and model into data/
```

The sandbox used so far could reach PyPI, npm, conda-forge and git over GitHub, but not Hugging
Face, Docker registries, Elastic or rechtspraak.nl. Those are proxy policy denials, so report them
and do not hunt for ways around them. Other options inside that policy: `beacon fetch-model` for
the model, and OpenSearch from conda-forge with `tests/tools/opensearch_shim.py` for a Lucene
engine. OpenSearch refuses to run as root, so use a separate user. Scripts that read a downloaded
checkout must live outside it, and any Python started in it needs `-I`.

## Map of beacon/

| Path | What it is |
| --- | --- |
| `src/beacon/sources/rechtspraak.py` | API client and XML parser |
| `src/beacon/sources/algoritmekader.py` | Real Dutch text with audit and requirement labels |
| `src/beacon/sources/files.py` | PDF, DOCX, HTML and text folders, ACL rules, ingest report, sync plan |
| `src/beacon/citations.py` | Statute citations to canonical form, for pages and queries |
| `src/beacon/synonyms.py` | Reviewable synonym list, BM25 only |
| `src/beacon/routing.py` | Language detection and term coverage, sets the BM25 weight |
| `src/beacon/groundedness.py` | Checks each claim against its cited passage |
| `src/beacon/auth.py` | Users, tokens, sessions, throttle, audit log |
| `src/beacon/web.py` | Web app, HTTP API, MCP over HTTP per user |
| `src/beacon/chunking.py` | Paragraph-aware chunks |
| `src/beacon/embeddings.py` | `st:`, `onnx:`, `spacy:` and `hash` embedders, plus a disk cache |
| `src/beacon/compounds.py` | Dutch compound splitting |
| `src/beacon/injection.py` | Planted-instruction evaluation and rule-based guard |
| `src/beacon/injection_holdout.py` | Payloads unseen by the rules. Never tune on these |
| `src/beacon/labelling.py` | `beacon pool` and `beacon label` for human judgements |
| `src/beacon/backends/` | `elastic.py` and the in-process `local.py` |
| `src/beacon/retrieval.py` | Client-side RRF and linear fusion, collapse to documents |
| `src/beacon/rag.py` | Generators and citation checks |
| `src/beacon/evaluate.py` | Metrics, bootstrap, permutation test, cross-validation |
| `src/beacon/quality.py` | Data quality report |
| `src/beacon/mcp_server.py` | Read-only MCP tools |
| `src/beacon/demo/` | Synthetic corpus and labelled queries |
| `evals/` | Plans, experiment runners, frozen configs, labels. `experiment3.py`, `experiment_grounded.py` and `scale.py` are the third run |
| `tests/tools/opensearch_shim.py` | Runs the Elasticsearch path on OpenSearch, for sandboxes |
| `reports/` | Measured results, committed |

## Rules that keep this honest

- **Report only what you measured.** Say which embedder, backend and corpus produced a number.
  Never present demo numbers as real-world quality.
- **Keep the evaluation clean.** No summaries in the index for known-item runs, no tuning on test
  queries, and report results that disappoint as well.
- **The holdout is spent.** `reports/ak-holdout.md` was scored once. `experiment.py holdout`
  refuses to run again, on purpose. New ideas need new test queries, or get called exploratory.
  Tune on `split == "dev"`, and never look at test queries first.
- **So are the fresh queries and the claim test half.** `experiment3.py score` and
  `experiment_grounded.py test` refuse a second run. Write new queries or claims, and a new plan
  committed first, for any new idea.
- **Do not edit the injection rules to catch holdout payloads.** Add new payloads instead, score
  them once, and only then consider a rule.
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

**Real Elasticsearch (do this first).** Follow "Needs Baris" in `PROGRESS.md`, then compare kNN
on the engine with the exact search behind the reported numbers. For rechtspraak.nl, expect the
parser to meet real XML that differs from the fixture. Save the shape of the problem as a new synthetic
fixture, not the real document.

**Search quality.** Add one idea at a time, and judge it with `beacon eval --baseline <current>`
on the same queries. Known-item runs catch regressions, while hand-labelled queries judge quality.
When a change wins on one and loses on the other, trust the hand labels and say so.

**RAG.** Run `beacon eval-rag --generator ollama:<model>` to compare with the extractive baseline.
Add a groundedness check that verifies claims against the cited passage; today only the citation
numbers are verified.

**MCP.** Keep tools read-only. Text from documents is untrusted and stays labelled as such.
Groups must never become a tool argument. Over HTTP, each user has a server bound to their groups.

**Web app.** No JavaScript, so the strict content policy can stay. Everything from a document goes
through `esc`. `result_item` and `answer_block` are the only places that build result HTML. Run the
UI in Playwright after changes: `tests/test_web.py` cannot see layout.

**Injection.** `beacon inject-eval --generator ollama:<model>` measures a real model. Exposure is
an upper bound, and the leak column is the real result. Run it without the guard as well.

**Template work.** See `beacon/PRIVATE_SEARCH_TEMPLATE.md`. Folder ingest, per-user tokens and an
audit log exist. Single sign-on, directory groups and OCR are next.
