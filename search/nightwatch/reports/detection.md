# What fires on labelled attack logs

Plan: [`evals/PREREGISTRATION.md`](../evals/PREREGISTRATION.md). Numbers:
[`detection-tuned.json`](detection-tuned.json), and an
[R cross-check](b2-mixed-model.txt). Scored once on the test split: 78 lab datasets from
Security-Datasets (commit `d9d40ef1`), 560,704 Windows events, 2,412 `rules/windows` rules from
SigmaHQ (commit `52f81d60`). Engine: **OpenSearch 3.9**, `tuned` setup, chosen on dev.

| Measure | Result |
| --- | --- |
| Rules that can fire at all on these logs (readiness) | 2,292 of 2,427 (94%) |
| Rules that did fire | 214 of 2,412 (9%) |
| Datasets with any alert | 77 of 78 |
| **Datasets with an on-target alert** | **53 of 78, 68%** (57 to 77) |
| Same, using only rules dated before the dataset | **33 of 78, 42%** |
| On-target share of (rule, dataset) firing pairs | 22% of 618 |
| Queries refused by the engine | 5, all Lucene or engine size limits on regexes and clauses |

Readiness gaps: 57 rules lack a field, led by `Data` (28 rules), 63 lack a log source and 15 name a
source Nightwatch cannot place.

## Planned tests

| # | Claim | Result | p (Holm) | Verdict |
| --- | --- | --- | --- | --- |
| B1 | All rules find more than rules that predate the dataset | 53 against 33, 20 datasets differ and none the other way | under 0.001 | Supported |
| B2 | High and critical rules are more often on target than low and medium | 30.3% against 21.8%, +8.5 points | 0.082 | **Not supported** |

R mixed model for B2 (`on_target ~ severe + (1|rule) + (1|dataset)`): same sign, one-sided
p = 0.075, Wald interval on the log-odds -1.63 to 10.66. The two methods agree that this is
unsettled. Ignore the model's point estimate: with most rules firing on very few datasets, the
rule-level variance is huge and the interval is the honest part.

## What this says

- **"Any alert" is nearly worthless as a measure.** 77 of 78 sounds like near-total detection, but
  background rules fire everywhere. `User Logoff Event` fired on 55 datasets.
- **Scoring old logs with new rules flatters the rules.** Recall falls from 68% to 42% with a date
  filter. Some of the gap is real progress, and some is that rules were written after, and possibly
  from, these same public logs. This design cannot separate the two. Either way, recall on a
  public dataset is not a forecast for the next attack.
- **Rule severity did not clearly help.** Do not use it alone to rank what to read first.
- **A quarter of the datasets got no on-target alert**, 25 of 78. Several are discovery commands that
  look like normal administration, such as `net group`, but read the list before concluding that:
  `missed_by_all` in the JSON.

## Exploratory: the same run on other setups

Not planned as tests. Same logs, same rules.

| Setup | On-target recall | Firing pairs | Total hits | On-target share |
| --- | --- | --- | --- | --- |
| `tuned` | 53 of 78 | 618 | 4,973 | 22% |
| Chunked, no CIDR or regex rewrite | 53 of 78 | 694 | 5,762 | 20% |
| Default dynamic mapping | 33 of 78 | 2,075 | **349,504** | **3%** |

- **A default mapping is worse in both directions.** Recall falls by more than a third while hits
  rise seventy-fold. An exact path is analysed into tokens that are joined by OR, so a rule for one
  DLL path matches events that merely share a token like `windows`: `Potential RjvPlatform.DLL
  Sideloading` alone produced 56,803 hits. A quiet index and a noisy one can have the same cause.
- **The CIDR and regex rewrites removed 77 firing pairs and added 1**, at no loss in recall. 49 of
  the 77 were one rule, `External Remote SMB Logon from Public IP`, firing on private addresses
  because its exclusion was a string that matched nothing. Another 23 came from a filter regex in
  `Uncommon Svchost Command Line Parameter` that had the same effect.

## Limits

- **No benign baseline.** These are lab logs with attacks in them, so an off-target alert is not a
  false positive. Attacks chain, and tags are incomplete. The share above is a proxy.
- **Dataset labels are coarse**, and parent-level matching is generous.
- **Date filter is an upper bound.** A rule edited after its date still counts as predating.
- **Sysmon-centred.** Process events from the Windows security log are not read as process creation.
- **Field presence, not behaviour.** A `ready` rule is able to fire. It may still be wrong.
