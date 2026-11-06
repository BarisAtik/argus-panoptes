# Watchtower progress

Newest run on top. Each run: read this, continue from the TODO, and update it.

## Current state (2026-11-06, second run)

Beacon now has real results. Everything still runs without Elasticsearch itself, which this
sandbox cannot download.

### What was actually verified

| Check | Result |
| --- | --- |
| Unit tests and ruff | 158 passed, clean |
| Algoritmekader fetch and parse | Live over git, pinned to `ade6b24e`, rebuilt identically |
| Real `multilingual-e5-small` | Quantised ONNX, runs on 2 CPU cores, Dutch and English sane |
| Elasticsearch code path, real client over HTTP | 10 of 10 integration tests pass, against OpenSearch 3.9 with the shim, now committed |
| Lucene analysis | `dutch`, the compound filter and the ACL `terms` filter ran on Lucene 10.5 |
| Retrieval evaluation | Plan committed first, dev tuning, holdout scored once on 99 queries |
| ACL | 13 tests, including a real MCP client. 4 of 4 deliberate faults caught |
| MCP over real stdio on the real corpus | Works (`evals/mcp_smoke.py`) |

### Not verified: do not assume these work

- **Never run on real Elasticsearch.** Hosts for Elastic, Docker Hub and Hugging Face returned 403
  from the proxy, so `dense_vector`, `int8_hnsw`, `knn` and `num_candidates` have never met a
  real server. All reported vector numbers come from exact search.
- **Never run against live rechtspraak.nl.** Also a proxy denial. I did not look for copies of it,
  and used a different public source instead.
- **Containers never started.** The Docker tag `9.5.5` is still unchecked.
- **No LLM has been run.** There is no local model here, so RAG results are extractive only and
  injection "leak" numbers say nothing about a real model.
- **The ONNX weights come from a third-party npm package**, `dsh-plugin-discover-model`. The hash
  is pinned, but it has not been compared with Hugging Face. See "Needs Baris".
- **`--subject` values and the Ollama and Anthropic generators** remain untested.

### Results so far

On the Algoritmekader, see `beacon/README.md` and `beacon/reports/`:

- Holdout nDCG@10: BM25 0.508, dense 0.509, RRF 0.545, tuned 0.595. Tuned beat RRF (+0.050, Holm
  p = 0.005). RRF did not significantly beat either BM25 or dense (Holm p = 0.209 both).
- Repeating the title in each chunk gave nearly all of the gain (+0.047, exploratory).
- On 41 short hand-written queries, dense beat BM25 by +0.190. English queries on Dutch text: dense
  0.882, BM25 0.425, RRF 0.707. Weak labels: one AI annotator.
- Injection rules: 9 of 9 known payloads, **0 of 12 unseen payloads**, 0 false positives.

### Decisions made this run

- Used the Algoritmekader as the real corpus, since rechtspraak.nl is blocked. Its audit mappings
  give labels I did not write, which is better evidence than the original plan.
- Ranked only measures in both labelled tasks, because labels cover only measures.
- Dropped reference lists and label-derived sections from the index to prevent leakage. This
  costs statute lookup.
- Wrote hand labels myself rather than leave them blank, and said so in the report.
- **A bug surfaced after the holdout.** The decompounder treated `aanbieders` as a compound of
  `aanbieder`. That quirk supplied the dev gain that kept compounds in the frozen config. I fixed
  it, left the holdout report as scored (code from `92c1496`), and added `ak-ablation.md`. With
  the fix, the frozen config scores 0.597 on the same queries, so the headline barely moves, but
  that number is exploratory.
- The rule "keep each change that gains 0.005" combined three changes. Together they scored
  0.606 on dev, below title prefix alone (0.608). Recommended defaults are therefore
  `--title-prefix` and RRF k=60, with compounds off unless measured on your own data.

## TODO, in priority order

1. Run the steps in "Needs Baris" 1 to 3, and fix what breaks. Compare HNSW with exact search.
2. Baris re-judges a sample of `evals/hand-labels.jsonl` with `beacon label`. Report agreement.
3. Language routing: skip or down-weight BM25 for non-Dutch queries. Write new test queries first.
4. Keep statute references in a separate keyword field, so `artikel 14 AI-verordening` works
   without leaking labels. Also add synonyms such as DPIA and gegevensbeschermingseffectbeoordeling.
5. Run injection with a real local model through `beacon inject-eval --generator ollama:<model>`.
   Then test output-side checks, since detection failed on unseen wording.
6. Add a claim-level groundedness check. Today only citation numbers are verified.
7. Cross-encoder reranker. No ONNX reranker was found on npm, so this needs Hugging Face.
8. Add more Dutch public text as distractors, such as the Logius standards (CC-BY 4.0), to make
   a harder and bigger corpus. Measure latency and index size at that scale.
9. Known-item evaluation on 500+ rechtspraak decisions once that source is reachable.
10. Per-user authentication for MCP over HTTP.

## Needs Baris

1. **First real run.** `cp .env.example .env`, set passwords, `docker compose up -d elasticsearch`,
   then `BEACON_IT=1 ELASTIC_PASSWORD=... pytest -m integration`. Then `make real-data` and
   `beacon ingest --corpus data/ak/corpus.jsonl --title-prefix --recreate --embedder
   onnx:data/models/multilingual-e5-small`. Also try `beacon fetch --date-from 2024-01-01
   --date-to 2024-01-07 --max-docs 20`.
2. **Check the model hash.** Compare the SHA-256 of `model_quantized.onnx`, `f80102d3...c98c193`,
   with the file page of `Xenova/multilingual-e5-small` on Hugging Face. Or use `st:` and download
   the original, which needs `pip install -e ".[embed]"`, a 2+ GB install.
3. **Enable CI.** Copy `search/beacon/ci/search-ci.yml` to `.github/workflows/search-ci.yml`. It
   was left there because this agent only writes in `search/`. It runs the integration tests on
   real Elasticsearch, which closes the biggest gap above.
4. **Install Ollama** with a model that handles Dutch, for local RAG.
5. **Re-judge some hand labels.** `beacon pool` then `beacon label`, about 30 minutes for 10
   queries. Only a person can settle whether the labels are any good.
6. **Decide on the licence of this code.** The repo has no LICENSE file. That is a root-level
   decision, and it matters if the template is ever sold or reused.

## Earning money: honest notes

| Idea | How | Realism |
| --- | --- | --- |
| Fixed-scope search audit | Take a client's existing search or RAG, label queries with them, and deliver a measured report using `beacon eval`. The evaluation harness is what most teams lack. `reports/ak-holdout.md` is now a real sample report, and the finding that the best method depends on the queries is the sales pitch | **Medium.** Best fit: low build cost and it shows skill. Needs a first client, and that takes outreach rather than code |
| RAG security check | Run `inject-eval` and ACL tests against a client's RAG or MCP setup, and report what gets through. The 0 of 12 result makes the case for it | **Medium-low.** Demand is growing, but buyers expect a track record. Pairs well with the audit above |
| Self-hosted document search pilot | Deploy on a client's own machine for firms that cannot send files to a cloud. Elastic's FAQ allows a contractor to do this. The torch-free ONNX route makes the install small | **Medium-low.** Real need. Group permissions now exist, but document parsing and a UI are missing, and Microsoft-based tools are the incumbent. Weeks of work, then a long sales cycle |
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

- Algoritmekader: EUPL-1.2 on [its repository](https://github.com/MinBZK/Algoritmekader), read from
  the LICENSE file. Text is downloaded at run time, and only 41 hand-written queries plus document
  ids are committed. `wordfreq` word lists are CC-BY-SA 4.0 and are not stored here.

## Run log

### 2026-11-06: second run

Found a route to real data, model and Lucene within the sandbox's allowed hosts. Added the
Algoritmekader source and labels, the ONNX embedder with a disk cache, compound splitting, access
control, the injection evaluation, `pool` and `label`, the OpenSearch shim, and the preregistered
evaluation. Two commits show the order: `92c1496` has the plan and no results.

### 2026-11-05: first run

Built `beacon/` from nothing. Wrote the synthetic demo corpus (35 documents, 34 queries including 4
unanswerable). Added leakage-free known-item evaluation, a paired significance test and
cross-validated fusion tuning. Did not look for mirrors of the blocked data.
