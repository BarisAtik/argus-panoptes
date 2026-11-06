# Holdout on the Algoritmekader

> Scored once on 99 test queries, measures only.
> Embedder onnx:multilingual-e5-small, in-process backend. Frozen config: {'max_words': 220, 'overlap_words': 40, 'title_prefix': True, 'compounds': True, 'rrf_k': 30}.
> Labels come from the Algoritmekader project, and are probably incomplete.

Queries: 99. Brackets are 95% bootstrap intervals.

| Run | mrr@10 | ndcg@10 | ndcg@5 | recall@10 | recall@5 |
| --- | --- | --- | --- | --- | --- |
| bm25 | 0.578 [0.50, 0.66] | 0.508 [0.44, 0.58] | 0.502 [0.43, 0.58] | 0.596 [0.52, 0.68] | 0.536 [0.45, 0.62] |
| dense | 0.581 [0.49, 0.67] | 0.509 [0.43, 0.59] | 0.490 [0.41, 0.57] | 0.553 [0.47, 0.64] | 0.480 [0.39, 0.57] |
| rrf | 0.607 [0.53, 0.69] | 0.545 [0.47, 0.62] | 0.524 [0.45, 0.60] | 0.643 [0.56, 0.72] | 0.552 [0.47, 0.64] |
| frozen | 0.660 [0.58, 0.74] | 0.595 [0.53, 0.66] | 0.588 [0.52, 0.66] | 0.681 [0.60, 0.76] | 0.615 [0.53, 0.70] |

## Paired comparisons

| Run vs baseline | Mean nDCG@10 diff | 95% CI | W/L/T | p | p (Holm) |
| --- | --- | --- | --- | --- | --- |
| rrf vs bm25 | +0.037 | [-0.006, +0.081] | 37/21/41 | 0.104 | 0.209 |
| rrf vs dense | +0.036 | [-0.013, +0.086] | 34/27/38 | 0.145 | 0.209 |
| frozen vs rrf | +0.050 | [+0.019, +0.084] | 36/15/48 | 0.002 | 0.005 |

## nDCG@10 by query type

| Type | n | bm25 | dense | rrf | frozen |
| --- | --- | --- | --- | --- | --- |
| audit-ADR | 37 | 0.665 | 0.658 | 0.733 | 0.798 |
| audit-ARK | 33 | 0.575 | 0.601 | 0.608 | 0.679 |
| requirement | 29 | 0.231 | 0.213 | 0.233 | 0.242 |
