# Evaluation card: Dutch named-entity recognition

Written before the first run. Results are added below the hypotheses afterwards, and the
hypotheses themselves are not edited after that point: see the Git history.

## Question

Named-entity recognition is the quiet first step in many document pipelines (search, redaction,
knowledge graphs). So: how far can a Dutch tagger be trusted once it leaves its home corpus, once
the input looks like a speech transcript, and when the names in the text aren't the names it grew
up with?

## Data

CoNLL-2002 Dutch: four 2000 editions of the Belgian newspaper De Morgen, with PER, LOC, ORG and
MISC. `ned.train` trains, `ned.testa` tunes, `ned.testb` tests once. Sentences are shuffled inside
each article for copyright reasons, so document context isn't available. Reasons for concern are
listed under data quality below.

**Licence:** the corpus README allows research use in the context of the shared task and excludes
other uses, commercial ones in particular. So: the data is never redistributed, no sentence is
committed here, and models trained on it stay local and are never sold or hosted. The spaCy Dutch
pipelines are CC BY-SA 4.0 according to their own metadata.

## Systems

| System | What it is |
| --- | --- |
| `gazetteer` | Baseline: longest case-sensitive lookup of entity strings from training |
| `nl_core_news_sm/md/lg` | spaCy 3.8 CNN pipelines trained on a different Dutch corpus (Lassy) |
| `deduce` | DEDUCE 3, rules and lookup lists built for Dutch medical text (added before any test score) |
| `own` | BiLSTM-CRF in plain PyTorch: frozen fastText-style vectors, char CNN, word shape |
| `own_aug` | Same, with half of the training sentences turned into transcript style each epoch |

Own models use seeds 0, 1 and 2. Follow-up analyses use the seed with the best dev F1.

## Metrics, fixed in advance

- Entity-level exact match on span and label (the CoNLL definition).
- `shared` scope: PER, LOC, ORG. The primary comparison with spaCy, because its MISC-like labels
  are a different scheme. `all` scope adds MISC.
- spaCy labels are mapped by `label_map.py`: PERSON to PER; GPE, LOC, FAC to LOC; ORG to ORG; NORP,
  EVENT, PRODUCT, WORK_OF_ART, LANGUAGE, LAW to MISC. Other labels are dropped.
- Intervals are 95% percentile bootstraps over **articles**. Paired comparisons use the same
  resamples for both systems, with Holm correction across the five comparisons in the report.
- Transcript style: lowercase and no punctuation tokens. It stands in for speech-to-text output
  and isn't real speech-to-text output.
- Name swap: every gold PER span is replaced with a name from one of five hand-written lists of
  common names (Dutch, Turkish, Moroccan, Polish, Surinamese-Hindustani), over 5 random repeats
  with identical designs. Score: exact PER recall. Gaps are against the Dutch list.

## Pre-registered hypotheses

1. **Vectors help.** `lg` beats `sm` by at least 2 points of shared F1, interval excluding zero.
2. **Corpus shift hurts.** `lg` scores at least 10 points below the 0.764 entity F1 in its own
   metadata. Rough comparison, because the label sets differ.
3. **Home advantage.** `own` beats `lg` on shared F1 by at least 5 points, interval excluding
   zero, because it learned this corpus's annotation habits. Best seed all-label F1 between 0.78
   and 0.86.
4. **Baseline.** `own` beats `gazetteer` by at least 20 points on all-label F1.
5. **Transcript damage.** Transcript style costs `lg` and `own` at least 25 points of shared F1.
6. **Augmentation pays.** `own_aug` wins back at least half of the transcript loss of `own`, and
   costs at most 2 points on clean text.
7. **Memorisation.** Recall on mentions unseen in training is at least 15 points below recall on
   seen mentions for `own`.
8. **Overconfidence.** Raw span confidence has ECE above 0.03, temperature fitted on dev cuts it by
   at least 30%, and on transcript-style input ECE stays at least twice the clean ECE after scaling.
9. **Names.** For at least one spaCy model and at least one list, exact PER recall is at least 3
   points below the Dutch list. `own` has a smaller worst gap than `lg`. The mixed model in R
   agrees on direction.
10. **Articles matter.** The article-level interval on F1 is at least 1.3 times as wide as a
    sentence-level one.
11. **Gold isn't gold.** In a random sample of 100 spans where `own` and `lg` agree against the
    gold labels, at least 25 are annotation errors or defensible both ways. Review by Claude
    against the sentence, not by a trained annotator. Verdicts are recorded by position only.
12. **The right tool for the wrong text.** Added before any test score was computed. On clean news
    text DEDUCE leaves at least 5 points more person-name tokens visible than `lg`, and on the
    non-Dutch lists its any-overlap recall is at least 5 points below its Dutch recall.

Metric for 12: `missed_tokens`, the share of gold PER tokens that no predicted PER, LOC or ORG span
covers, because a redactor doesn't care about the label.

## Results

Added after the runs, commit `000e588`, 6 Nov 2026. Hypotheses above are unchanged. All intervals
95%, over articles. Follow-up analyses use the best-dev seeds, `own_s1` and `own_aug_s1`.

| # | Verdict | Evidence |
| --- | --- | --- |
| 1 | Supported | `lg` minus `sm`: 14.7 points (12.0 to 17.4), Holm p 0.001 |
| 2 | **Wrong** on the primary scope | Shared F1 0.704 is 6.0 points below 0.764. Only on all four labels (0.655) is the drop over 10 |
| 3 | Supported | `own` minus `lg`: 17.7 points (14.1 to 21.7). Best-dev seed all-label F1 0.858 |
| 4 | Supported | 27.6 points (24.6 to 30.6) |
| 5 | Supported, and an underestimate for `own` | `lg` loses 28.3 points, `own` 87.0 |
| 6 | Supported | `own_aug` wins back 80% of the loss. Clean cost 0.0 points (-0.9 to 0.8) |
| 7 | Supported | Recall 0.945 on seen against 0.770 on unseen mentions, gap 17.5 |
| 8 | Supported, with a caveat | ECE 0.040 to 0.017. Transcript ECE after scaling is 2.9 times clean for `own_aug`. `own` only made 15 spans there, so its figure means nothing |
| 9 | Supported | `lg` worst gap 40.8 points, `own` 8.8. R agrees on direction for every gap that is clear in both |
| 10 | Supported | Article interval 1.58 times as wide as the sentence one |
| 11 | Met exactly, weak | 25 of 100, 2 true gold errors, 23 defensible, 16 distinct strings. Reviewer knew the threshold |
| 12 | Supported | Name tokens left visible on clean text: DEDUCE 27.4%, `lg` 8.7%. DEDUCE any-overlap recall: Dutch list 1.000, others 0.556 to 0.889 |

**Surprises.** Hypothesis 5 undersold it badly: without capital letters `own` tags almost nothing.
Augmentation had no measurable clean cost, where a small one was expected. `sm` is no better than
the lookup baseline on clean text, a warning against small pipelines off their home corpus. On name swaps
`sm` recalls the Turkish list better than the Dutch one (+5.5 points), so the gaps are not one
simple story about familiarity. They may depend on the hand-picked names.

**Deviations and things to know.**
- The corpus is UTF-8 in the NLTK copy, not Latin-1. The parser crashed on this before any score.
- `evaluate` crashed once on sentences emptied by transcript style, before any score was printed.
  The fix touched only that path.
- `names_why` and the person baseline are post hoc, and labelled so.
- Hypothesis 2 didn't name a scope. The card calls `shared` primary, so that decides it.
- Hypothesis 12 was added during training, before any test score. Own dev F1 was already visible.

## Follow-up: per-name audit (registered 2026-11-06, before any per-name or Faker score)

The swap gaps were known when these were written. Per-name recall and every Faker list were not.
Model `nl_core_news_lg`, exact PER recall, 5 repeats, code in `name_audit.py`. Faker has no
Moroccan or Surinamese-Hindustani table, so only Dutch, Turkish and Polish can be checked this way.

13. **Not a handful.** Dropping the three worst names from the Hindustani and the Turkish list
    keeps at least two thirds of each gap.
14. **Lists.** With names and articles resampled, the Hindustani and Turkish gaps still exclude 15
    points on the favourable side (upper bound below -0.15).
15. **Word frequency.** Across the hand lists, Spearman between a name's Zipf frequency in Dutch and
    its recall is at least 0.3.
16. **Independent lists.** With Faker tables, the Turkish gap against Faker Dutch is at least 15
    points and Polish at least 5, both intervals excluding zero.
17. **Diacritics.** Folding accents changes recall by less than 3 points for both Faker lists.

## Known limits

- One newspaper, one region, one year. Nothing here says how Dutch from the Netherlands, social
  media or legal text behaves.
- Name lists are hand-written and short. The R model treats the name as a random effect to reflect
  that, but it can't fix what the lists leave out.
- The swap ignores grammatical gender and context fit, and all swapped text is synthetic.
- Own models were tuned on `ned.testa` by early stopping only, with fixed architecture.
