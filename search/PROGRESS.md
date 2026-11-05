# Watchtower progress

Newest run on top. Each run: read this, continue from the TODO, and update it.

## Current state (2026-11-05, first run)

`beacon/` works end to end on the synthetic demo set: chunking, embeddings, BM25, kNN, client-side
RRF and linear fusion, RAG with citation checks, evaluation, data quality report, MCP server,
Docker Compose stack.

### What was actually verified

| Check | Result |
| --- | --- |
| Unit tests and ruff | 104 passed, clean |
| Mutation check on 15 hand-picked faults | All caught, after 3 survivors led to stronger tests |
| Elasticsearch code path, real client over HTTP | 9 of 9 integration tests pass, against **OpenSearch 3.9 with a throwaway shim** |
| CLI ingest, search, ask, eval on that server | Work |
| MCP over real stdio as a subprocess | Works |
| `docker compose config` | Passes, including the Kibana profile |

### Not verified: do not assume these work

This run's sandbox blocked rechtspraak.nl, Elastic's download and image hosts, and Hugging Face.
Docker had no daemon. So:

- **Never run against real Elasticsearch.** Expect small surprises. The OpenSearch stand-in shares
  Lucene and most of the query language, but it is a different product.
- **kNN and HNSW are untested on a live engine.** OpenSearch's k-NN plugin was not in the package,
  so the shim did the cosine maths. `dense_vector`, `int8_hnsw`, the `knn` search option and
  `num_candidates` never reached a server.
- **Never run against live rechtspraak.nl.** The client and parser come from technical docs v1.15
  (2019) and synthetic XML. Real documents may differ, and paging `from` may be 0- or 1-based
  (sources disagree, so the client deduplicates).
- **Containers never started.** Compose syntax is valid, nothing more. The Docker tag `9.5.5` was
  inferred from a GitHub release tag, and the image tag itself was not checked.
- **The default model `multilingual-e5-small` never loaded.** Dense results here come from spaCy
  Dutch word vectors, a much simpler method. Expect different numbers.
- **`--subject` values are unchecked.** `dcterms:subject` text and the
  `rechtsgebied` URIs need confirming against `/Waardelijst/Rechtsgebieden`.
- **Ollama and Anthropic generators have no live test.** Only the prompt building and citation
  checks are covered.

### Results so far

All on the synthetic demo set, see `beacon/reports/`. They test the pipeline only. The main lesson:
RRF did not beat dense on nDCG@10 (-0.035, CI -0.116 to +0.046, p = 0.42), though it had the best
recall@10. Lexical queries are too easy, and I wrote both queries and documents. Real labels matter.

## TODO, in priority order

1. Run the steps in "Needs Baris" 1 to 3, and fix what breaks.
2. Known-item evaluation on 500+ real decisions with e5, against BM25 and spaCy.
3. Label 50+ real queries by pooling the top 10 of each run. Write a small `beacon label` command.
   Include hard queries: paraphrases, legal concepts, and queries with a statute number.
4. Dutch compound splitting. Try Elasticsearch's `hyphenation_decompounder` and measure it. Probably
   the biggest cheap win for BM25.
5. Add a local cross-encoder reranker, and measure the gain against the extra latency.
6. RRF `k` and chunk-size sensitivity runs. Add latency and index-size measurements.
7. Real RAG evaluation with a local Ollama model, including a claim-level groundedness check.
8. Prompt-injection test set: plant instructions in documents, and measure how often they work.
9. Ingest other Dutch open data, to show the pipeline is not tied to one source.
10. Add document-level access control, the first requirement for the template.

## Needs Baris

1. **First real run.** `cp .env.example .env`, set passwords, `docker compose up -d elasticsearch`,
   then `BEACON_IT=1 ELASTIC_PASSWORD=... pytest -m integration`. Then `beacon fetch --date-from
   2024-01-01 --date-to 2024-01-07 --max-docs 20` and `beacon quality --corpus data/corpus.jsonl`.
2. **Load the model.** `pip install -e ".[embed]"` and `beacon ingest --corpus data/corpus.jsonl
   --recreate`. The first run downloads the model, and torch is a 2+ GB install.
3. **Enable CI.** Copy `search/beacon/ci/search-ci.yml` to `.github/workflows/search-ci.yml`. It
   was left there because this agent only writes in `search/`. It runs the integration tests on
   real Elasticsearch, which closes the biggest gap above.
4. **Install Ollama** with a model that handles Dutch, for local RAG.
5. **Decide on the licence of this code.** The repo has no LICENSE file. That is a root-level
   decision, and it matters if the template is ever sold or reused.

## Earning money: honest notes

| Idea | How | Realism |
| --- | --- | --- |
| Fixed-scope search audit | Take a client's existing search or RAG, label queries with them, and deliver a measured report using `beacon eval`. The evaluation harness is what most teams lack | **Medium.** Best fit: low build cost and it shows skill. Needs a first client, and that takes outreach rather than code |
| Self-hosted document search pilot | Deploy on a client's own machine for firms that cannot send files to a cloud. Elastic's FAQ allows a contractor to do this | **Medium-low.** Real need, but document parsing, permissions and a UI are all missing, and Microsoft-based tools are the incumbent. Weeks of work, then a long sales cycle |
| Dutch case-law alerts | A subscription by legal area, using the public data | **Low-medium.** Data is free to use, and someone already sells a similar monitor on Apify, which shows both demand and competition. Legal publishers dominate this market |
| Sell the template | Paid repo or starter kit | **Low.** Plenty of free RAG templates exist. The Dutch evaluation angle helps, but it is a niche |
| Paid MCP server | Hosted search tool for agents | **Low.** No clear buyer, and hosting Elasticsearch for others runs into its licence if customers reach the engine directly |

Nothing here has been tested on the market. These are judgements, not data, and income from any of
them is uncertain. Competition prizes do not really apply to this folder.

### Licence facts checked

- rechtspraak.nl dataset: listed as Public Domain on [data.overheid.nl](https://data.overheid.nl/dataset/uitspraken-rechtspraak-nl).
  That is a catalogue label. The [technical documentation](https://www.rechtspraak.nl/SiteCollectionDocuments/Technische-documentatie-Open-Data-van-de-Rechtspraak.pdf)
  itself states no licence. Decisions can still hold personal data, so public domain does not settle
  privacy duties. Get proper advice before any commercial use.
- Service limits, from the [open data page](https://www.rechtspraak.nl/Uitspraken/paginas/open-data.aspx):
  at most 10 requests per second, and no full-dataset download.
- Elastic: [ELv2 FAQ](https://www.elastic.co/licensing/elastic-license/faq) on managed services and
  contractors. RRF and linear retrievers being Enterprise-only comes from a
  [third-party article](https://dev.to/u11d/reciprocal-rank-fusion-on-free-elasticsearch-licensing-workarounds-and-the-opensearch-alternative-56jk).
  Confirm on Elastic's subscriptions page.

## Run log

### 2026-11-05: first run

Built `beacon/` from nothing. Wrote the synthetic demo corpus (35 documents, 34 queries including 4
unanswerable). Added leakage-free known-item evaluation, a paired significance test and
cross-validated fusion tuning. Did not look for mirrors of the blocked data.
