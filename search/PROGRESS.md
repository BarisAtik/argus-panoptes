# Watchtower progress

Newest run on top. Each run: read this, continue from the TODO, and update it.

## Current state (2026-11-06, fourth run)

The third run committed its work but never updated this file, so its results are summarised below
from the commits and reports. This run repaired that and added a second project, `nightwatch/`.

### What was actually verified

| Check | Result |
| --- | --- |
| Beacon unit tests and ruff | 233 passed, 17 integration skipped, clean |
| Nightwatch tests and ruff | 55 unit and 5 integration passed, clean |
| Nightwatch on a live Lucene engine | OpenSearch 3.9, Lucene 10.5, 560,704 events, 2,412 rules, no shim needed |
| Nightwatch evaluation | Plan committed in `eda3201`, test split scored once. R model run on lme4 2.0.6 |
| Nightwatch MCP over real stdio | Works against the engine and against SQLite |
| Algoritmekader fetch and parse | Live over git, pinned to `ade6b24e`, rebuilt identically |
| Real `multilingual-e5-small` | Quantised ONNX, runs on 2 CPU cores, Dutch and English sane |
| Beacon on a Lucene engine | 10 of 10 integration tests, through the OpenSearch shim |
| Beacon retrieval evaluations | Three one-shot evaluations, plans committed first |
| Beacon web app and MCP over HTTP | Tested, and run in a browser by the third run |

### Not verified: do not assume these work

- **Neither project has run on real Elasticsearch.** Hosts for Elastic, Docker Hub and Hugging Face
  were refused by the proxy again this run, so `dense_vector`, `int8_hnsw`, `knn` and
  `num_candidates` have never met a real server, and every Nightwatch number is OpenSearch 3.9.
- **Never run against live rechtspraak.nl.** Also a proxy denial. I did not look for copies of it.
- **Containers never started.** The Docker tag `9.5.5` is still unchecked.
- **No LLM has been run.** RAG results are extractive only, and injection "leak" numbers say
  nothing about a real model.
- **The ONNX weights come from a third-party npm package**, `dsh-plugin-discover-model`. The hash
  is pinned, but it has not been compared with Hugging Face. See "Needs Baris".
- **Nightwatch has no benign baseline**, so it reports no false-positive rate. ES|QL and EQL are
  printed, never executed. No Kibana dashboards exist.
- **`--subject` values and the Ollama and Anthropic generators** remain untested.

### Nightwatch results

See `nightwatch/reports/`. All on OpenSearch 3.9.

- Of 380 rules, on their own positive samples: default dynamic mapping fires 20%, raw keyword 77%,
  lowercase keyword 93%, tuned (chunking, regex and CIDR rewrites) 98%, SQLite reference 99%.
- `wildcard` fields fired only 9% through `query_string`. It looks like a path quirk: a direct
  `wildcard` query matched. Not a result about Elasticsearch.
- On 78 labelled lab datasets: an on-target alert on 68%, and 42% with only rules dated before the
  dataset (p under 0.001). Severity did not significantly predict being on target (p = 0.082).
- Exploratory: the default mapping gave 33 of 78 on target and 70 times the hits.

### Decisions made this run

- **Started a second project instead of more Beacon features.** Beacon's remaining TODO is blocked
  on hosts or on Baris. Nightwatch could run on a real Lucene engine today, and adds detection work
  next to document search.
- **Sigma's own regression samples as labels.** No human or AI judgment needed, and nobody here
  wrote them. Cleaner than any labels Beacon has.
- **Added `keyword_lower_chunked` and `tuned` after reading dev results**, before test was touched,
  and said so in the plan. Dev also chose `tuned` for Experiment B. CIDR expansion went in after a
  dev run of Experiment B, also before test.
- **Plain REST rather than the Elasticsearch client**, so no shim was needed.
- **No A2A work here.** `red-teaming/hermes` already covers A2A in this repo.
- **Rule author added to MCP alerts** after reading DRL 1.1, which requires it.
- **Sandbox note:** I briefly loosened permissions on the session's temp folder to start OpenSearch,
  found that was not needed, restored them and moved the engine to its own user's home. Nothing
  from that reached the repo.

### Third run, summarised

Routing, synonyms and citation matching, a claim-level groundedness check, folder ingest for PDF,
DOCX and HTML, a web app with per-user tokens and an audit log, and MCP over HTTP.

- Skipping BM25 for non-Dutch queries: 0.548 to 0.793 nDCG@10 (+0.245, Holm p under 0.001). No Dutch
  query changed. Dense alone stayed level with or ahead of every hybrid on these 62 fresh queries.
- Synonyms: not supported (+0.003). Labels from two AI annotators, weighted kappa 0.485.
- Claim check: 72% of written false claims flagged, with 12% false alarms. 42% of subtle errors
  got through.

### Beacon results from the second run

On the Algoritmekader, see `beacon/README.md` and `beacon/reports/`:

- Holdout nDCG@10: BM25 0.508, dense 0.509, RRF 0.545, tuned 0.595. Tuned beat RRF (+0.050, Holm
  p = 0.005). RRF did not significantly beat either BM25 or dense (Holm p = 0.209 both).
- Repeating the title in each chunk gave nearly all of the gain (+0.047, exploratory).
- On 41 short hand-written queries, dense beat BM25 by +0.190. English queries on Dutch text: dense
  0.882, BM25 0.425, RRF 0.707. Weak labels: one AI annotator.
- Injection rules: 9 of 9 known payloads, **0 of 12 unseen payloads**, 0 false positives.

### Decisions from the second run

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

1. **Real Elasticsearch, both projects.** Run the steps in "Needs Baris" 1 to 3 and fix what breaks.
   For Beacon, compare HNSW with exact search. For Nightwatch, rerun `regress` under a new plan and
   settle the `wildcard` question.
2. **Nightwatch: a benign baseline.** Find public benign Windows logs, or build a small lab, so that
   false positives can be measured. Without it, no precision claim is possible.
3. **Nightwatch: fresh attack data.** `datasets/compound` is unused. Plan first, and use it to test
   whether the rule date filter holds up, then look at the 25 datasets with no on-target alert.
4. **Nightwatch: field name fixes.** Normalise `New Value` to `NewValue`, and canonicalise IPv6.
   Both are known silent failures. They need new samples to score, since the test split is spent.
5. **Nightwatch: ECS logs.** Most real clusters use ECS fields, not native Windows names. Add the
   `ecs_windows` pipeline and make `nightwatch audit` work on them. This is what decides whether
   the audit is useful to anyone with a real cluster.
6. **Nightwatch: Kibana dashboard** for readiness and alerts, as a saved-objects file. Needs real
   Kibana to test.
7. Baris re-judges a sample of `evals/hand-labels.jsonl` with `beacon label`. Report agreement.
8. Run Beacon injection with a real local model through `beacon inject-eval --generator
   ollama:<model>`, then test output-side checks. Do the same for a log-borne planted instruction
   through Nightwatch's MCP tools, since a command line can hold one.
9. Cross-encoder reranker for Beacon, and an entailment model for claim checks. Needs Hugging Face.
10. Known-item evaluation on 500+ rechtspraak decisions once that source is reachable.

## Needs Baris

1. **First real run.** In `beacon/`: `cp .env.example .env`, set passwords, `docker compose up -d
   elasticsearch`, then `BEACON_IT=1 ELASTIC_PASSWORD=... pytest -m integration`. Then `make real-data` and
   `beacon ingest --corpus data/ak/corpus.jsonl --title-prefix --recreate --embedder
   onnx:data/models/multilingual-e5-small`. Also try `beacon fetch --date-from 2024-01-01
   --date-to 2024-01-07 --max-docs 20`.
2. **Check the model hash.** Compare the SHA-256 of `model_quantized.onnx`, `f80102d3...c98c193`,
   with the file page of `Xenova/multilingual-e5-small` on Hugging Face. Or use `st:` and download
   the original, which needs `pip install -e ".[embed]"`, a 2+ GB install.
3. **Enable CI.** Copy `search/beacon/ci/search-ci.yml` to `.github/workflows/search-ci.yml` and
   `search/nightwatch/ci/nightwatch-ci.yml` to `.github/workflows/nightwatch-ci.yml`. They were left
   there because this agent only writes in `search/`. They run the integration tests on real
   Elasticsearch, which closes the biggest gap above.
4. **Install Ollama** with a model that handles Dutch, for local RAG.
5. **Re-judge some hand labels.** `beacon pool` then `beacon label`, about 30 minutes for 10
   queries. Only a person can settle whether the labels are any good.
6. **Decide on the licence of this code.** The repo has no LICENSE file. That is a root-level
   decision, and it matters if the template is ever sold or reused.

## Earning money: honest notes

| Idea | How | Realism |
| --- | --- | --- |
| Detection readiness audit | Run `nightwatch audit` on a team's own Elastic or OpenSearch cluster, read-only, and report which rules cannot fire and why. Fixed price, one or two days. The 20% to 98% table is the pitch, and it is easy to verify on their own index. Fit for teams with an in-house SIEM and no detection engineer | **Medium.** Best idea in this folder: cheap to deliver, read-only so it is easy to approve, and the result is concrete. Blockers: it needs ECS support (TODO 5), an Elasticsearch run, and a first client. Security buyers want references, and tool vendors already offer coverage views |
| Fixed-scope search audit | Take a client's existing search or RAG, label queries with them, and deliver a measured report using `beacon eval`. The evaluation harness is what most teams lack. `reports/ak-holdout.md` is now a real sample report, and the finding that the best method depends on the queries is the sales pitch | **Medium.** Best fit: low build cost and it shows skill. Needs a first client, and that takes outreach rather than code |
| RAG security check | Run `inject-eval` and ACL tests against a client's RAG or MCP setup, and report what gets through. The 0 of 12 result makes the case for it | **Medium-low.** Demand is growing, but buyers expect a track record. Pairs well with the audit above |
| Self-hosted document search pilot | Deploy on a client's own machine for firms that cannot send files to a cloud. Elastic's FAQ allows a contractor to do this. The torch-free ONNX route makes the install small | **Medium-low.** Real need. Group permissions now exist, but document parsing and a UI are missing, and Microsoft-based tools are the incumbent. Weeks of work, then a long sales cycle |
| Dutch case-law alerts | A subscription by legal area, using the public data | **Low-medium.** Data is free to use, and someone already sells a similar monitor on Apify, which shows both demand and competition. Legal publishers dominate this market |
| Sell the template | Paid repo or starter kit | **Low.** Plenty of free RAG templates exist. The Dutch evaluation angle helps, but it is a niche |
| Paid MCP server | Hosted search tool for agents | **Low.** No clear buyer, and hosting Elasticsearch for others runs into its licence if customers reach the engine directly |

Nothing here has been tested on the market. These are judgements, not data, and income from any of
them is uncertain. Competition prizes do not really apply to this folder. A clear public write-up of
the mapping result is the cheapest way to find out whether anyone cares, and it is ready to draft
from `nightwatch/reports/`.

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

- Sigma rules: [Detection Rule License 1.1](https://github.com/SigmaHQ/Detection-Rule-License),
  read in full this run. It allows commercial use and sale, and keeps the author on shared rules and
  on messages based on matches. Security-Datasets: MIT, read from the LICENSE file.

## Run log

### 2026-11-06: fourth run

Found that the third run left this file stale, and repaired it. Built `nightwatch/`: pinned data
sources, Lucene and SQL conversion, six mapping variants plus chunking and rewrites, readiness and
audit, statistics, MCP tools and an R cross-check. Plan committed first in `eda3201`, then scored.

### 2026-11-06: third run

See "Third run, summarised" above. Reconstructed by the fourth run from the commits.

### 2026-11-06: second run

Found a route to real data, model and Lucene within the sandbox's allowed hosts. Added the
Algoritmekader source and labels, the ONNX embedder with a disk cache, compound splitting, access
control, the injection evaluation, `pool` and `label`, the OpenSearch shim, and the preregistered
evaluation. Two commits show the order: `92c1496` has the plan and no results.

### 2026-11-05: first run

Built `beacon/` from nothing. Wrote the synthetic demo corpus (35 documents, 34 queries including 4
unanswerable). Added leakage-free known-item evaluation, a paired significance test and
cross-validated fusion tuning. Did not look for mirrors of the blocked data.
