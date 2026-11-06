# Routing, synonyms and citations: fresh queries, scored once

Plan: [`evals/PREREGISTRATION-3.md`](../evals/PREREGISTRATION-3.md). Corpus: Algoritmekader, all
198 pages. Embedder: quantised `multilingual-e5-small`. Backend: local, with exact vector search.
Numbers: [`ak-routing.json`](ak-routing.json). Results from another engine will differ.

The router was frozen on seen queries before this run. It chose the language detector over term
coverage (0.699 against at most 0.684 on the 41 seen queries).

Labels came from two AI annotators, working separately on shuffled blind pools. **No person has
judged these**, and agreement was only moderate (weighted kappa 0.485 over 337 pairs).

## Planned tests

| # | Test | n | Variant | Baseline | Difference (95% interval) | p (Holm) | Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Router on non-Dutch queries | 29 | 0.793 | 0.548 | +0.245 (0.158 to 0.336) | under 0.001 | Supported |
| 2 | Router on Dutch queries | 23 | 0.746 | 0.746 | 0.000 (0.000 to 0.000) | n/a | Supported: it changed nothing |
| 3 | Synonyms on abbreviation queries | 10 | 0.764 | 0.761 | +0.003 (-0.089 to 0.073) | 0.496 | **Not supported** |
| 4 | Citation list on statute lookups | 128 | 0.393 | 0.244 | +0.149 (0.111 to 0.189) | under 0.001 | Supported, see caveat |

With the second annotator's labels, tests 1 and 2 hold (+0.244 and 0.000). Test 3 reads +0.035
(0.007 to 0.070, one-sided p = 0.031 before correction), so that result depends on who judged.

## All variants, nDCG@10 on 62 fresh queries

| Run | All | recall@10 | English (23) | Other (6) | Dutch (23) | Abbreviations (10) |
| --- | --- | --- | --- | --- | --- | --- |
| BM25 | 0.434 | 0.515 | 0.223 | 0.189 | 0.632 | 0.615 |
| Dense | **0.789** | 0.828 | 0.784 | 0.827 | 0.766 | 0.827 |
| RRF | 0.656 | 0.778 | 0.482 | 0.801 | 0.746 | 0.761 |
| Routed | 0.775 | 0.849 | 0.784 | 0.827 | 0.746 | 0.791 |
| Routed + synonyms + citations | 0.781 | **0.854** | 0.784 | 0.827 | 0.746 | 0.825 |

## What this says

- **Routing is worth having.** A small detector removes the damage BM25 does to non-Dutch queries,
  and no Dutch query changed.
- **Dense alone still came first on ranking here.** Routing brings hybrid level with dense, not
  past it. Dense scored 0.766 on Dutch against 0.746 for RRF. This was not a planned comparison, so
  treat it as exploratory. Hybrid keeps a small lead on recall@10.
- **These queries favour dense.** They are short and conceptual, written by someone who knows the
  topic but not the wording. Formal audit queries gave BM25 and dense equal scores in the second
  evaluation. Which method wins depends on the queries.
- **Synonyms did little in hybrid.** The dense list already handles abbreviations (0.827), and
  routing alone moved these queries to 0.791. Adding synonyms and citations on top gave 0.825, an
  exploratory number. BM25 is where the list would matter, and the first annotator's result does
  not support it as a separate step.
- **Citations: read test 4 with care.** Labels and the citation field come from the same pages and
  the same extractor, so the gain partly measures the plumbing. It does show that wordings such as
  `Article 22 GDPR` now reach pages they could not reach before (English 0.251 to 0.574). The scores
  stay low because a page's citation enters as one of three lists in RRF, and an article cited
  by many pages spreads over them.
- **The small test sets limit all of this.** Ten abbreviation queries cannot detect a small effect.

## Limits

- Queries, labels and synonym list come from AI, and the same author wrote the queries and the plan.
- All from one 198-page corpus. The router would need a new list of languages for other collections.
- Pool depth 10 from the runs above, so unjudged documents count as not relevant. All compared runs
  are in the pool, which limits that bias.
- Five queries have no page graded 2 by the first annotator, and score from grade 1 alone or zero.
