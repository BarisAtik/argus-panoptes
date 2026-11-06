# Evaluation card: Dutch redaction under register shift

Written before the first run, including the first run on dev. The hypotheses below stay as they
are: results are added underneath. Git history shows the order.

## Question

News-trained taggers get measured on news. Personal data lives in letters, chat, call transcripts
and terse case notes. How much leaks when a local Dutch redactor meets those, and do simple,
checkable rules help?

## Data

Fully synthetic and free of real people. Hand-written templates in six registers (`brief`, `mail`,
`chat`, `transcript`, `beschikking`, `notitie`) get filled at run time with fictional combinations
of names, addresses and numbers. Generated documents are never committed, because a random number
that passes a format check can coincide with a real one by chance.

- **dev**: 24 templates by the rule author. Rules may be tuned here.
- **test**: 36 templates, written by a separate agent that had no access to the redactor and was
  told not to read it. The rule author does not read this file until rules are frozen.
- Each template is crossed with five naming traditions and 8 repeats. Draws are paired.
- Rules may not use the benchmark's name, street or town lists. That would be scoring the answer key.

## Systems

| System | What it is |
| --- | --- |
| `patterns` | `ner_nl.redact` patterns only, no model |
| `spacy_sm`, `spacy_md`, `spacy_lg` | Patterns plus the spaCy Dutch pipeline |
| `deduce` | DEDUCE 3, all annotations |
| `rules` | Tuned on dev: extended patterns and context rules, no statistical model |
| `rules_lg` | `rules` plus `spacy_lg`, with names propagated through the document |

## Metrics, fixed in advance

- **Leak rate.** A value leaks if any word in it stays readable. `S. Bakker` with `S.` left is a leak.
- **Over-redaction.** Share of ordinary words masked. Reported apart for distractors (amounts, case
  numbers, ordinary dates, clock times). Towns are neutral: counted neither way.
- **Intervals** are cluster t intervals over templates, the real unit of replication.

## Pre-registered hypotheses

1. **News models leak.** `spacy_lg` leaks at least 15% of person values on test.
2. **Register matters.** For `spacy_lg`, person leak in `transcript` is at least twice that in `brief`.
3. **Spoken digits are invisible.** `spacy_lg` leaks at least 80% of spoken phone numbers and BSNs.
4. **Names.** For `spacy_lg`, at least one non-Dutch tradition leaks at least 5 points more person
   values than the Dutch list, with an interval excluding zero.
5. **Home turf.** `deduce` beats `spacy_lg` on person leak in `brief` and `beschikking`, and loses in
   `chat` and `transcript`.
6. **Rules pay.** `rules_lg` at least halves the all-kinds leak of `spacy_lg` on test, while
   over-redaction of ordinary words rises by at most 2 points.
7. **Tuning flatters.** The all-kinds leak of `rules_lg` on test is at least 1.5 times its dev leak.
8. **Unit of analysis.** The template-level interval on the `spacy_lg` person leak is at least 1.5
   times as wide as a document-level one.

## Known limits

- Templates are not real documents, and their fills are randomly combined. This benchmark finds
  failures. It does not estimate the leak rate of any real archive.
- Both template authors are language models, so the register styles are imitations.
- Name lists are short and hand-written, shared with `ner_nl`.
- Transcript style here is simulated, with idealised spelled-out digits.

## Results, first scoring of test (2026-11-06)

Rules were frozen in commit `cf0404a` before test was read or scored. Full tables:
[test](../results/pii_nl/test.md), [dev](../results/pii_nl/dev.md). 36 templates, 5 traditions, 8
repeats, 6120 values. Intervals are 95% cluster t over templates.

| # | Prediction | Outcome | Verdict |
| --- | --- | --- | --- |
| 1 | `spacy_lg` leaks at least 15% of persons | 30.4% (21.7 to 39.1) | Confirmed |
| 2 | Transcript at least twice brief | 64.8% against 16.7%, 3.9 times | Confirmed |
| 3 | At least 80% of spoken phone numbers and BSNs leak | 100% of 80 values | Confirmed, but only 2 templates hold such values |
| 4 | A tradition at least 5 points above Dutch | Hindustani +31.1 (23.2 to 39.0), Turkish +24.7, Moroccan +16.9, Polish +7.9 | Confirmed |
| 5 | DEDUCE wins in `brief`, `beschikking`; loses in `chat`, `transcript` | Wins 10.4 against 16.7 and 5.8 against 16.3, loses transcript 100 against 64.8, **wins chat** 46.3 against 54.1 | Half right: chat prediction wrong |
| 6 | `rules_lg` halves all-kinds leak, ordinary masking up by at most 2 points | 34.8% to 7.5%; masking 1.2% to 3.1% | Confirmed, the masking limit only just |
| 7 | Test leak at least 1.5 times dev | 7.5% against 3.2%, 2.3 times | Confirmed |
| 8 | Template interval at least 1.5 times document interval | 17.4 against 4.1 points, 4.3 times | Confirmed |

**Reading this honestly.** `rules_lg` still leaks 12.9% of persons (3.9 to 21.8), and 32.5% in chat
and 41.1% in transcripts, which is not good enough to run unreviewed. Nearly all of that is
lowercase text, where neither casing cues nor the news model help. The tradition gap shrinks with
rules (Hindustani +10.9, interval -0.5 to 22.2) but this does not show it is gone. Rate estimates
describe this template set, not any real archive.

## Second round, pre-registered 2026-11-06

After first scoring, `test` is spent: it may now be read and used for tuning, and its numbers above
stay as recorded. A new blind set, `test2`, has 36 templates by a fresh agent with the same brief,
different topics, and more phone and BSN slots. It is scored once, with seed 1, after rules freeze.

New system `rules_lg_tc`: `rules_lg`, but lowercase lines are truecased before the news model reads
them. Words rare in general Dutch (by `wordfreq`) get a capital. Offsets don't change.

9. **Replication.** `rules_lg` all-kinds leak on `test2` falls inside the `test` interval, 2.5% to
   12.4%.
10. **Truecasing pays.** `rules_lg_tc` lowers person leak in `chat` plus `transcript` by at least 10
    points against `rules_lg` on `test2`, with ordinary-word masking up by at most 1 point.
11. **Common-word surnames stay hard.** On `test2` with `rules_lg_tc`, the Dutch list, whose surnames
    are often ordinary words, leaks more persons than the mean of the other four lists in `chat`
    plus `transcript`.

### Results, second round (2026-11-06)

`test2`, seed 1, 36 templates, 5720 values, rules frozen in commit `965281a`. Tables:
[test2](../results/pii_nl/test2.md).

| # | Prediction | Outcome | Verdict |
| --- | --- | --- | --- |
| 9 | `rules_lg` all-kinds leak inside 2.5% to 12.4% | 6.0% (2.6 to 9.5) | Confirmed |
| 10 | Truecasing cuts lowercase-register person leak by at least 10 points, masking up at most 1 | 27.3% to 15.8%, paired cut 11.6 points (2.9 to 20.2); masking 1.8% to 2.4% | Confirmed |
| 11 | Dutch list leaks more than the mean of the others in lowercase registers | 14.1% against 16.2% | **Wrong** |

Best system: `rules_lg_tc` leaks 4.8% of all values (1.9 to 7.6) and 5.6% of persons (2.0 to 9.1).
For comparison `spacy_lg` leaks 30.9% and DEDUCE 23.5% on the same documents. The lowercase
registers still leak about 16%.

**A flaw in the freeze.** The commit that froze round two had one failing new test, which was
overlooked and seen only after scoring. The spoken-plate rule treated single letters as common
words, so it hardly ever fired. The fix came after scoring, so the numbers above are from the
buggy version, which understates plate handling. A new blind set would be needed to quote the fix.
