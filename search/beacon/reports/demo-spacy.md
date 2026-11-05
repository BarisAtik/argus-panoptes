# Demo corpus, Dutch word vectors

> SYNTHETIC demo corpus, written by the author of the queries. These numbers test the pipeline. They do not estimate performance on real documents.
> Embedder: spacy:nl_core_news_md. Backend: local.
> linear(cv): alpha tuned on other folds; chosen per fold: [0.1, 0.1, 0.1, 0.1, 0.1].

Queries: 30. Brackets are 95% bootstrap intervals.

| Run | mrr@10 | ndcg@10 | ndcg@5 | recall@10 | recall@5 |
| --- | --- | --- | --- | --- | --- |
| bm25 | 0.594 [0.43, 0.76] | 0.613 [0.45, 0.78] | 0.613 [0.45, 0.78] | 0.667 [0.50, 0.83] | 0.667 [0.50, 0.83] |
| dense | 0.791 [0.66, 0.91] | 0.816 [0.70, 0.92] | 0.816 [0.70, 0.92] | 0.933 [0.83, 1.00] | 0.933 [0.83, 1.00] |
| rrf | 0.725 [0.59, 0.85] | 0.781 [0.67, 0.88] | 0.757 [0.63, 0.87] | 0.967 [0.90, 1.00] | 0.900 [0.77, 1.00] |
| linear(cv) | 0.765 [0.63, 0.88] | 0.796 [0.68, 0.90] | 0.784 [0.66, 0.90] | 0.933 [0.83, 1.00] | 0.900 [0.80, 1.00] |

## Paired comparisons

| Run vs baseline | Mean nDCG@10 diff | 95% CI | W/L/T | p | p (Holm) |
| --- | --- | --- | --- | --- | --- |
| dense vs bm25 | +0.203 | [+0.070, +0.343] | 10/2/18 | 0.007 | 0.014 |
| rrf vs bm25 | +0.168 | [+0.082, +0.259] | 11/1/18 | 0.001 | 0.003 |
| linear(cv) vs bm25 | +0.183 | [+0.061, +0.312] | 10/2/18 | 0.008 | 0.014 |

## nDCG@10 by query type

| Type | n | bm25 | dense | rrf | linear(cv) |
| --- | --- | --- | --- | --- | --- |
| lexical | 12 | 1.000 | 1.000 | 1.000 | 1.000 |
| paraphrase | 18 | 0.355 | 0.694 | 0.635 | 0.660 |
