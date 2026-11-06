# BM25 on Lucene, with and without compound splitting

100 dev queries, measures only, default chunks. Word lists of 2595 and 28217 words. Exploratory. The engine is OpenSearch 3.9 on Lucene 10.5, used because Elasticsearch could not be downloaded. Settings come from `index_body`.

| Analyzer | nDCG@10 | recall@10 |
| --- | --- | --- |
| dutch | 0.545 | 0.613 |
| compounds, corpus words | 0.547 | 0.630 |
| compounds, corpus and common words | 0.566 | 0.643 |

Paired sign-flip test on nDCG@10, common-word list vs plain: p = 0.303.

Tokens for `algoritmeregister`: `algoritmeregister algoritm register`.
Tokens for `verantwoordelijkheid`: `verantwoord verantwoord lijk`, which shows the cost: Lucene finds words inside words, so noise like `lijk` gets in.

The in-process BM25 on the same queries scored 0.573 (`ak-dev-tuning.md`).
