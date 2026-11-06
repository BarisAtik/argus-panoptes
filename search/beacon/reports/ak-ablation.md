# Which part of the frozen config helped? Exploratory

Post-hoc look at the 99 test queries, rrf mode, code after the decompounder fix. Not a second holdout. p-values are unadjusted.

| Config | nDCG@10 | recall@10 | diff vs default | p |
| --- | --- | --- | --- | --- |
| default | 0.545 | 0.643 | +0.000 | 1.000 |
| title prefix | 0.592 | 0.682 | +0.047 | 0.008 |
| title prefix, k=30 | 0.586 | 0.666 | +0.041 | 0.024 |
| frozen, decompounder fixed | 0.597 | 0.672 | +0.052 | 0.002 |
