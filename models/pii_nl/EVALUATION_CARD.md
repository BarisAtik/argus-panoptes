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
| `rules_lg` | `rules` plus `spacy_lg` |

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
