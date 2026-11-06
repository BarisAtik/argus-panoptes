# Does a rule fire on its own test sample? Mapping decides

Plan: [`evals/PREREGISTRATION.md`](../evals/PREREGISTRATION.md). Numbers:
[`regression.json`](regression.json). Scored once on the test split, 380 Windows rules, each with
the positive sample that Sigma ships for it. Engine: **OpenSearch 3.9 on Lucene 10.5.** Rule set:
SigmaHQ commit `52f81d60`. Results on Elasticsearch may differ, and it has not been run there.

| Index setup | Rules that fire | Share (95% interval) | Exact count | Failed queries |
| --- | --- | --- | --- | --- |
| Default dynamic mapping (`text`) | 75 | **19.7%** (16.0 to 24.0) | 74 | 3 |
| `wildcard` field, through `query_string` | 34 | 8.9% | 34 | 4 |
| `keyword`, raw | 294 | 77.4% | 292 | 3 |
| `keyword`, lowercase, `ignore_above: 1024` | 352 | 92.6% | 350 | 3 |
| `keyword`, lowercase, `ignore_above: 8191` | 354 | 93.2% | 352 | 3 |
| Same, long values stored as overlapping pieces | 365 | 96.1% | 363 | 3 |
| Same, plus regex and CIDR rewrites (`tuned`) | 372 | **97.9%** (95.9 to 98.9) | 370 | 3 |
| SQLite reference | 375 | 98.7% | 373 | 4 |

No engine or mapping reported a problem for a missed rule. A failed query is an error; everything
else in the gap is a silent zero.

## Planned tests

| # | Claim | Gained | Lost | p (Holm) | Result |
| --- | --- | --- | --- | --- | --- |
| A1 | Lowercase keyword beats raw keyword | 60 | 0 | under 0.001 | Supported |
| A2 | Lowercase keyword beats dynamic text | 284 | 5 | under 0.001 | Supported |
| A3 | `ignore_above: 8191` beats 1024 | 2 | 0 | 0.25 | **Not supported** |
| A4 | Chunking long values beats plain keyword | 11 | 0 | 0.001 | Supported |
| A5 | Regex and CIDR rewrites beat chunking alone | 7 | 0 | 0.016 | Supported |

A4 and A5 were added after reading dev results, before test was touched. A3 failed because most of
the damage is above 8,191 characters as well: raising the limit does not reach those values, which
is what chunking fixes. The 5 cases lost in A2 are long scripts: they survive as text tokens and
are dropped by `ignore_above`, which is why chunking is needed on top.

## Why rules go quiet

Read by hand, as planned. Of the 23 rules where `keyword_lower` and SQLite disagree:

| Cause | Rules | Fixed by |
| --- | --- | --- |
| Value longer than `ignore_above`, so not indexed | 11 | Chunking |
| Lucene regex matches the whole term, and a normalizer leaves the pattern alone | 7 | Rewrite |
| Regex too expensive for Lucene's automaton limit, or a clause limit | 3 | Nothing yet. These are errors, not zeros |
| `\b` in a regex, which Lucene does not have | 1 | Nothing yet |
| SQL missing a column, so here Lucene was right | 1 | Not a Lucene problem |

Four rules fired on nothing anywhere, and an exploratory look found two more silent classes:

- **Three Defender rules.** The logs say `New Value` and `Source Name`, and the rules say `NewValue`
  and `SourceName`. Nothing joins them, so the rule never matches. A field rename fixes it.
- **One IPv6 rule.** The log holds `0:0:0:0:0:0:0:1`, and the rule's CIDR is `::1/128`. Same
  address, two spellings.

## The odd one: `wildcard`

The field type built for this job did worst. On a one-event test, a native `wildcard` query matched
and the same pattern through `query_string` did not, when the pattern ended in literal text. So
this looks like a property of that path on OpenSearch 3.9 and not of the field type. **Do not read
it as a result about Elasticsearch's `wildcard` field.** Test that first.

## Limits

- Positive samples only. They show a rule can fire, not that it fires only when it should. Hits on
  other rules' samples rose from 150 to 169 with chunking and rewrites; SQLite gave 171, so the
  rise looks like recovered matches, not new noise. That comparison was not planned.
- The samples are the rule authors' own, usually one or two events, and rarely hard cases.
- Chunking keeps patterns up to 1,024 characters whole. A suffix test can match the end of a piece,
  and the event's `_source` holds the pieces and not the original string. Keep the original as an
  unindexed field if you need it.
