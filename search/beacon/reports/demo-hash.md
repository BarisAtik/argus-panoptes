# Demo corpus, hash embedder

> SYNTHETIC demo corpus, written by the author of the queries. These numbers test the pipeline. They do not estimate performance on real documents.
> Embedder: hash:512. Backend: local.
> The hash embedder is a character n-gram method and not semantic. Its dense and hybrid rows are no evidence about embedding models.
> linear(cv): alpha tuned on other folds; chosen per fold: [0.3, 0.3, 0.3, 0.3, 0.3].

Queries: 30. Brackets are 95% bootstrap intervals.

| Run | mrr@10 | ndcg@10 | ndcg@5 | recall@10 | recall@5 |
| --- | --- | --- | --- | --- | --- |
| bm25 | 0.594 [0.43, 0.76] | 0.613 [0.45, 0.78] | 0.613 [0.45, 0.78] | 0.667 [0.50, 0.83] | 0.667 [0.50, 0.83] |
| dense | 0.611 [0.47, 0.75] | 0.676 [0.55, 0.80] | 0.644 [0.50, 0.78] | 0.883 [0.77, 0.98] | 0.783 [0.63, 0.92] |
| rrf | 0.717 [0.57, 0.86] | 0.750 [0.61, 0.88] | 0.740 [0.59, 0.88] | 0.850 [0.72, 0.97] | 0.817 [0.67, 0.93] |
| linear(cv) | 0.676 [0.52, 0.82] | 0.716 [0.58, 0.84] | 0.694 [0.55, 0.83] | 0.850 [0.72, 0.97] | 0.783 [0.63, 0.92] |

## Paired comparisons

| Run vs baseline | Mean nDCG@10 diff | 95% CI | W/L/T | p | p (Holm) |
| --- | --- | --- | --- | --- | --- |
| dense vs bm25 | +0.062 | [-0.053, +0.182] | 8/6/16 | 0.323 | 0.323 |
| rrf vs bm25 | +0.137 | [+0.060, +0.226] | 9/0/21 | 0.004 | 0.012 |
| linear(cv) vs bm25 | +0.103 | [+0.020, +0.200] | 7/3/20 | 0.029 | 0.059 |

## nDCG@10 by query type

| Type | n | bm25 | dense | rrf | linear(cv) |
| --- | --- | --- | --- | --- | --- |
| lexical | 12 | 1.000 | 0.995 | 1.000 | 0.995 |
| paraphrase | 18 | 0.355 | 0.462 | 0.583 | 0.529 |
