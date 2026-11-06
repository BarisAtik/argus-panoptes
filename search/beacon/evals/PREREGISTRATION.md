# Evaluation plan, fixed before any retrieval result was seen

Written and committed before the first run on this corpus, so that the plan can be checked
against the git history.

## Data

Algoritmekader at commit `ade6b24e`: 198 pages (108 measures, 62 requirements, 28 tools).
Audit task: 139 norms from the Auditdienst Rijk and the Algemene Rekenkamer, mapped to measures
by the Algoritmekader project. Requirement task: 60 requirements, mapped to measures through page
metadata. Neither label set was written for this project. Only measures are ranked.

Queries split into `dev` and `test` on a SHA-256 of the query id, so no choice is involved.

## Tuning, on dev only

From the default (220 words, overlap 40, no title prefix, no compounds, RRF k=60), change one
thing at a time. Keep a change only if it raises mean nDCG@10 on dev by at least 0.005.

- chunk size 120/20 and 350/50
- title prefix on
- compound splitting on
- RRF k of 10, 30 and 100

The dev choices go to `evals/frozen.json`.

## Holdout, on test, scored once

Runs: `bm25`, `dense` and `rrf` at the defaults, and `frozen` (the hybrid chosen on dev). The
primary metric is nDCG@10, with recall@10 as secondary.

| Comparison | Expectation |
| --- | --- |
| rrf default vs bm25 default | hybrid wins |
| rrf default vs dense default | hybrid wins |
| frozen vs rrf default | tuning helps |

Paired sign-flip permutation tests with a Holm correction over these three, bootstrap intervals
on the differences. A result that goes the other way is reported as it is. Nothing is tuned after
the test run. Later ideas need new data, or get reported as exploratory.

## Hand-written queries

41 queries in `hand-labels.jsonl`, written before seeing any ranking, including 10 in English
to test the cross-lingual claim. Labelled from a pool of the top 10 of each run, by one AI
annotator (Claude) who saw titles and summaries but not which run returned them. That is the weakest of
the three label sets: one annotator, no agreement measure, and not a person. Baris should
re-judge a sample with `beacon label`.

## Known weaknesses

- The mappings name the best fits, not every relevant page, so absolute scores read low.
- Audit norms are longer and more formal than what people type, which may suit BM25 and dense
  differently. The hand-written set is there to check this.
- 198 pages is small. Latency and any effect of HNSW approximation are out of scope.
- All of this runs on the in-process backend, with Lucene checks on OpenSearch where stated.
  Elasticsearch itself could not be reached from the sandbox.

## Deviations, added after the runs

- Hand labels cover document titles and summaries, not full page text.
- `statute-02` has one label from outside the pool. No run returned the right page, `aia-09`, in
  its top 10. Leaving it out would have scored a miss as a success for the other documents.
- `frozen` stayed in the hand report as a fourth run, though it was not in the pool.
- The decompounder had a bug, found after the holdout. See `PROGRESS.md` and
  `reports/ak-ablation.md`. The holdout report is unchanged. `experiment.py dev` would now
  give a different frozen config, so `frozen.json` is the record of what was scored.
- `ablation` on test queries and the common-word list on dev queries were not in this plan.
  Both are labelled exploratory.
