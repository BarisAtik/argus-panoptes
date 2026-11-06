# Plan for the third evaluation: routing, synonyms and citations

Committed before any fresh query has been run through any ranker. The commit history is the proof.

## Why

The second evaluation showed BM25 dragging down English queries on Dutch text (hybrid 0.707, dense
0.882 on 10 queries), and statute lookup is weak because reference lists are not indexed. Those
queries have now been seen, so they can only be used for tuning.

## Data

- **Tuning:** the 41 queries in `hand-labels.jsonl`, already seen.
- **Fresh test:** the 64 queries in `fresh-queries.jsonl`, written before seeing any ranking on
  them: 24 English, 6 German, French or Spanish, 24 Dutch, 10 with abbreviations.
- **Corpus:** Algoritmekader at the pinned commit, all document types. Scored on all types, unlike
  the audit tasks, because these queries can have any page as their answer.
- **Labels:** a blind pool (depth 10 from BM25, dense, RRF and the routed variants, shuffled, no
  system names) judged 0, 1, 2 by two independent AI annotators working separately. The first
  annotator's labels are primary, the second gives agreement (weighted Cohen's kappa) and a
  sensitivity run. No person has judged these, so the results are weak evidence.
- **Statute lookup:** queries generated from a template for each law and article found in the
  `Bronnen` sections of requirement pages, with the citing pages as the relevant set. Half is for
  debugging, half is test, split by a hash of the query id. The same extractor reads the pages and
  the queries, so this test is partly circular. It shows that the plumbing and the wording variants
  work, and not that citation extraction is correct in general.

Two fresh queries turned out to repeat tuning queries word for word: `f-en-14` (AI literacy for
staff) and `f-nl-05` (verboden AI-praktijken). Found before scoring, so they are dropped from the
test, which leaves n=29 non-Dutch and n=23 Dutch.

## Fixed config

Embedder: quantised `multilingual-e5-small`. Local backend, `max_words=220`, `overlap_words=40`,
title prefix on, compounds off, RRF k=60. These are the recommended defaults from the second run.

## Variants

| Name | What it does |
| --- | --- |
| `rrf` | Baseline. Equal weight to BM25 and dense |
| `route-lang` | Language detector. Non-Dutch query: BM25 weight 0 |
| `route-coverage` | BM25 weight is the share of query terms found in the index, raised to a power |
| `synonyms` | Adds known synonyms and expansions to the BM25 query only |
| `refs` | A third ranked list of pages that cite the law and article named in the query |

On the 41 tuning queries, pick one router and its power from {1, 2, 4}, then freeze it in
`frozen-3.json` before scoring the fresh queries. Synonyms come from a list written without
looking at fresh-query rankings.

## Hypotheses, on nDCG@10

1. On non-Dutch queries (n=29), the frozen router beats `rrf`.
2. On Dutch queries (n=23), the frozen router is not worse than `rrf`: the 95% interval of the
   difference stays above -0.03.
3. On abbreviation queries (n=10), `synonyms` beats `rrf`.
4. On statute-lookup test queries, `refs` beats `rrf`.

Tests are one-sided in the expected direction with paired sign-flip permutation. Holm correction
is applied over 1, 3 and 4. Hypothesis 2 is judged by its interval alone. Fresh queries are scored
once. Anything tried after that gets called exploratory.
