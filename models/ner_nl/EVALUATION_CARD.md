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

## Known limits

- One newspaper, one region, one year. Nothing here says how Dutch from the Netherlands, social
  media or legal text behaves.
- Name lists are hand-written and short. The R model treats the name as a random effect to reflect
  that, but it can't fix what the lists leave out.
- The swap ignores grammatical gender and context fit, and all swapped text is synthetic.
- Own models were tuned on `ned.testa` by early stopping only, with fixed architecture.
