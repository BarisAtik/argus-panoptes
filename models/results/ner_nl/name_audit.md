# Name gap: per name and with independent lists

Model nl_core_news_lg, exact PER recall on swapped names, CoNLL-2002 Dutch test. Commit 527926f, 2026-11-06T07:03:04+00:00.

## Spread inside each list

| list | names | recall | worst | p25 | median | p75 | best |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dutch | 20 | 0.8709 | 0.5813 | 0.8138 | 0.9065 | 0.9498 | 0.9776 |
| turkish | 20 | 0.5732 | 0.3308 | 0.3909 | 0.6017 | 0.7667 | 0.8456 |
| moroccan | 20 | 0.7617 | 0.4517 | 0.5862 | 0.8409 | 0.8905 | 0.9338 |
| polish | 20 | 0.7723 | 0.5776 | 0.6689 | 0.7603 | 0.8743 | 0.9627 |
| hindustani | 20 | 0.4628 | 0.1931 | 0.3687 | 0.4122 | 0.4601 | 0.8427 |
| faker_dutch | 200 | 0.7213 | 0.0435 | 0.5814 | 0.7386 | 0.9250 | 1.0000 |
| faker_turkish | 60 | 0.2645 | 0.0145 | 0.1190 | 0.2090 | 0.3734 | 0.7500 |
| faker_polish | 200 | 0.6313 | 0.1429 | 0.5000 | 0.6382 | 0.7900 | 1.0000 |
| faker_polish_folded | 200 | 0.6392 | 0.1429 | 0.5000 | 0.6414 | 0.7900 | 1.0000 |
| faker_turkish_folded | 60 | 0.2794 | 0.0145 | 0.1377 | 0.2317 | 0.3936 | 0.7763 |

## Gaps with names and articles resampled

| list | reference | gap | low | high |
| --- | --- | --- | --- | --- |
| turkish | dutch | -0.2976 | -0.4017 | -0.1946 |
| moroccan | dutch | -0.1091 | -0.1973 | -0.0212 |
| polish | dutch | -0.0985 | -0.1801 | -0.0175 |
| hindustani | dutch | -0.4080 | -0.5115 | -0.3016 |
| faker_turkish | faker_dutch | -0.4568 | -0.5235 | -0.3901 |
| faker_polish | faker_dutch | -0.0900 | -0.1424 | -0.0379 |
| faker_polish_folded | faker_dutch | -0.0821 | -0.1356 | -0.0313 |
| faker_turkish_folded | faker_dutch | -0.4419 | -0.5075 | -0.3759 |

## Leave out the three worst names

| list | gap | gap_without_worst_3 |
| --- | --- | --- |
| turkish | -0.2976 | -0.2556 |
| moroccan | -0.1091 | -0.0637 |
| polish | -0.0985 | -0.0671 |
| hindustani | -0.4080 | -0.3750 |

Spearman of Dutch word frequency and recall, hand lists: 0.50 (p 1.24e-07, 100 names).

Post hoc, inside each list: dutch -0.16, turkish 0.18, moroccan 0.17, polish 0.20, hindustani 0.11.
