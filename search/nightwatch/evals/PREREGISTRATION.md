# Plan: do Sigma rules fire, and what does the index mapping do to them?

Written before any test result was seen. Seen so far: the shape of one log file, the channel counts of
the attack corpus, rule counts by status and level, and a one-event smoke test of the mappings on
an invented event, which is where the wildcard worry below comes from. That smoke test is the only
thing resembling a result, and it is the reason the wildcard variants are not in a planned test.

**Pins.** Sigma rules `52f81d60`, Security-Datasets `d9d40ef1`, pySigma 1.5.1, Lucene backend 2.1.1.
**Engine.** OpenSearch 3.9 on Lucene 10.5, because Elasticsearch cannot be downloaded where this
runs. SQLite is a second, in-process reference. Nothing here is a result about Elasticsearch.

## Data

- **Regression cases.** Sigma ships positive samples per rule, with the number of matches
  expected. Labels were written by rule authors, so "fires" here means "does what its own test
  says". Windows rules only. Keyword rules with no field are excluded, because their meaning
  depends on which field is searched, and counted.
- **Attack datasets.** Security-Datasets Windows atomic host logs: lab simulations, each tagged by
  its authors with ATT&CK techniques.
- **Split.** A salted hash sends one fifth of each to dev and the rest to test. All debugging
  happens on dev. Test is scored once, and `evals/experiment.py` refuses a second run.

## Experiment A: mapping and engine, on regression cases (test split)

Primary measure: the rule returns at least one hit on its own sample. Secondary: exactly the
expected count. Failed queries count as not firing, and are listed.

Variants: `dynamic_text`, `keyword_raw`, `keyword_lower`, `keyword_lower_1024`, `wildcard_raw`,
`wildcard_lower`, `keyword_lower_chunked`, `tuned`, and SQLite.

`keyword_lower_chunked` and `tuned` were **added after reading dev results**, before test was
touched. On dev, five long PowerShell scripts passed `ignore_above` and vanished from the index, and
regex rules behaved differently because Lucene matches the whole term. A CIDR filter on a keyword
field also matched nothing. So: `keyword_lower_chunked` stores long values as overlapping pieces,
and `tuned` adds a regex rewrite and CIDR expansion on top. Both are dev-tuned, so only test counts.

| # | One-sided claim | Test |
| --- | --- | --- |
| A1 | `keyword_lower` fires on more cases than `keyword_raw` | Exact McNemar |
| A2 | `keyword_lower` fires on more cases than `dynamic_text` | Exact McNemar |
| A3 | `keyword_lower` fires on more cases than `keyword_lower_1024` | Exact McNemar |
| A4 | `keyword_lower_chunked` fires on more cases than `keyword_lower` | Exact McNemar |
| A5 | `tuned` fires on more cases than `keyword_lower_chunked` | Exact McNemar |

Holm correction over A1 to A5, alpha 0.05. Any disagreement between `keyword_lower` and SQLite is
read by hand and classified. There is no directional claim about SQLite or the wildcard variants.

**Variant for Experiment B:** the Lucene variant with the highest firing rate on dev, ties going to
`keyword_lower`. It is chosen on dev only. On dev that was `tuned` (91 of 91 own samples).

## Experiment B: detection on attack logs (test split)

Rules: `rules/windows`, field-based, converted to Lucene. A rule counts for a dataset when its
query has at least one hit there.

| Measure | Definition |
| --- | --- |
| Readiness | Share of rules that can fire on the whole corpus, from `readiness.py`, with reasons |
| Any alert | Share of datasets where at least one rule fires |
| On-target recall | Share of datasets where a rule fires whose ATT&CK tags share a parent technique with the dataset |
| On-target share | Of all (rule, dataset) firing pairs, the share that are on target |

| # | One-sided claim | Test |
| --- | --- | --- |
| B1 | On-target recall with all rules exceeds recall using only rules dated on or before the dataset | Exact McNemar over datasets |
| B2 | On-target share is higher for high and critical rules than for low and medium | Permutation of level between rules, so a noisy rule counts once |

Holm over B1 and B2. Datasets created before Sigma's rule dates begin are kept, and they weigh
against pre-dated recall, which is why B1 is a statement about optimism and not about skill.

**R cross-check for B2.** `glmer(on_target ~ severe + (1 | rule) + (1 | dataset), binomial)` in
`evals/mixed_model.R`. If the sign or the 95% interval disagrees with the permutation test, both
are reported and B2 counts as unsettled.

**Exploratory, not tested.** The same detection run on `dynamic_text`, to show how many alerts a
default mapping loses, and a comparison of alerts with and without the CIDR expansion.

## What this cannot show

- **There is no benign baseline.** These are lab logs with attacks in them. An off-target alert is
  not a false positive: attacks chain, and tags are incomplete. On-target share is a proxy.
- **Rules may have been written from these logs.** The rule date filter only removes rules first
  published later. A rule edited after its date is still in the pre-dated set, so pre-dated recall
  is an upper bound.
- **Sysmon-centred.** Rule categories map to Sysmon events only, so process events from the
  Windows security log are not read as process creation.
- **Tags are coarse.** Parent-level matching is generous, and a dataset can carry one tag for
  behaviour that spans many.
