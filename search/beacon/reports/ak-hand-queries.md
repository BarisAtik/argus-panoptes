# Hand-written queries on the Algoritmekader

> 41 queries written before any ranking was seen, all page types ranked.
> Labels: one AI annotator (Claude), from a pool of bm25, dense and rrf at the defaults. `frozen` was not in the pool, which can only hurt it.
> Not a holdout: the same author wrote queries and labels, and tuning was done on other queries. Read this as a sanity check on short queries.

Queries: 41. Brackets are 95% bootstrap intervals.

| Run | mrr@10 | ndcg@10 | ndcg@5 | recall@10 | recall@5 |
| --- | --- | --- | --- | --- | --- |
| bm25 | 0.620 [0.50, 0.74] | 0.501 [0.40, 0.61] | 0.449 [0.34, 0.56] | 0.577 [0.47, 0.68] | 0.445 [0.35, 0.55] |
| dense | 0.808 [0.71, 0.90] | 0.691 [0.61, 0.77] | 0.623 [0.53, 0.71] | 0.795 [0.72, 0.86] | 0.594 [0.51, 0.68] |
| rrf | 0.799 [0.70, 0.89] | 0.631 [0.55, 0.71] | 0.579 [0.49, 0.67] | 0.707 [0.62, 0.79] | 0.570 [0.48, 0.66] |
| frozen | 0.814 [0.71, 0.91] | 0.678 [0.59, 0.76] | 0.603 [0.50, 0.70] | 0.743 [0.65, 0.83] | 0.569 [0.47, 0.67] |

## Paired comparisons

| Run vs baseline | Mean nDCG@10 diff | 95% CI | W/L/T | p | p (Holm) |
| --- | --- | --- | --- | --- | --- |
| dense vs bm25 | +0.190 | [+0.088, +0.292] | 30/8/3 | 0.001 | 0.001 |
| rrf vs bm25 | +0.129 | [+0.042, +0.211] | 30/7/4 | 0.004 | 0.004 |
| frozen vs bm25 | +0.177 | [+0.121, +0.237] | 33/2/6 | 0.000 | 0.000 |

## nDCG@10 by query type

| Type | n | bm25 | dense | rrf | frozen |
| --- | --- | --- | --- | --- | --- |
| en-cross | 10 | 0.425 | 0.882 | 0.707 | 0.737 |
| nl-paraphrase | 5 | 0.281 | 0.574 | 0.496 | 0.433 |
| nl-question | 10 | 0.551 | 0.523 | 0.559 | 0.651 |
| nl-short | 12 | 0.618 | 0.736 | 0.700 | 0.770 |
| statute | 4 | 0.493 | 0.643 | 0.580 | 0.631 |
