# Demo corpus, hash embedder, Lucene Dutch analyzer

> Embedder: hash:512. Backend: elastic code path against OpenSearch 3.9 through a test shim, not Elasticsearch; kNN scored by the shim.
> The hash embedder is a character n-gram method and not semantic. Its dense and hybrid rows are no evidence about embedding models.
> linear(cv): alpha tuned on other folds; chosen per fold: [0.7, 0.3, 0.3, 0.5, 0.3].

Queries: 30. Brackets are 95% bootstrap intervals.

| Run | mrr@10 | ndcg@10 | ndcg@5 | recall@10 | recall@5 |
| --- | --- | --- | --- | --- | --- |
| bm25 | 0.567 [0.40, 0.73] | 0.584 [0.42, 0.75] | 0.584 [0.42, 0.75] | 0.633 [0.47, 0.80] | 0.633 [0.47, 0.80] |
| dense | 0.611 [0.47, 0.75] | 0.676 [0.55, 0.80] | 0.644 [0.50, 0.78] | 0.883 [0.77, 0.98] | 0.783 [0.63, 0.92] |
| rrf | 0.706 [0.56, 0.85] | 0.742 [0.60, 0.87] | 0.732 [0.59, 0.87] | 0.850 [0.72, 0.97] | 0.817 [0.67, 0.93] |
| linear(cv) | 0.643 [0.50, 0.78] | 0.700 [0.57, 0.82] | 0.668 [0.52, 0.80] | 0.883 [0.77, 0.98] | 0.783 [0.63, 0.92] |

## Paired comparisons

| Run vs baseline | Mean nDCG@10 diff | 95% CI | W/L/T | p | p (Holm) |
| --- | --- | --- | --- | --- | --- |
| dense vs bm25 | +0.091 | [-0.027, +0.217] | 8/6/16 | 0.167 | 0.167 |
| rrf vs bm25 | +0.158 | [+0.074, +0.253] | 10/0/20 | 0.002 | 0.006 |
| linear(cv) vs bm25 | +0.116 | [+0.028, +0.217] | 8/3/19 | 0.021 | 0.041 |

## nDCG@10 by query type

| Type | n | bm25 | dense | rrf | linear(cv) |
| --- | --- | --- | --- | --- | --- |
| lexical | 12 | 1.000 | 0.995 | 1.000 | 0.995 |
| paraphrase | 18 | 0.307 | 0.462 | 0.570 | 0.502 |
