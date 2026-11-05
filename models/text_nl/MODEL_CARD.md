---
language: nl
license: cc-by-nc-sa-4.0
tags: [sentiment-analysis, dutch, text-classification]
datasets: [benjaminvdb/dbrd]
---

# Dutch book-review sentiment (draft card)

> **No model has been trained yet.** This card is the template and the pre-registration.
> Fill it from a `real` report. Publish no weights until "Results" is complete.

## Intended use

A demonstration of careful evaluation; sentiment of Dutch book reviews. Not suited for decisions
about people, and not for other domains without testing them first (the `other_domain` probes
exist to show how far it travels).

## Licence

DBRD is CC BY-NC-SA 4.0, so anything trained on it should be treated as non-commercial and
shared alike. Before publishing, also check the base model's own licence.

## Data

[DBRD](https://huggingface.co/datasets/benjaminvdb/dbrd): 20,028 train and 2,224 test reviews,
binary labels (van der Burgh & Verberne, 2019, arXiv:1910.00896). The dataset card itself warns of
imperfect language filtering, commercial promotions and spelling errors, and leaves its bias
section empty. Labels derive from star ratings, so "sentiment" here means "what the rater gave",
and mid-range reviews are probably absent, which makes the task easier than real text.

## Pre-registered hypotheses (written before any run)

1. The fine-tuned model beats TF-IDF by less than people expect on this easy task: under 5 points.
2. Raw transformer probabilities are overconfident; a temperature above 1 lowers ECE.
3. Head+tail truncation beats head-only on long reviews.
4. Both models do far worse on `sarcasm` and `understatement` than on plain sentences. Negation of
   negative phrases is worse than negation of positive ones.
5. Book-domain vocabulary helps: `other_domain_film_food_hotel` scores below `plain_*`.
6. The audit finds near-duplicates in test that also occur in train, and the honest accuracy
   without them is lower than the headline.

## Results

_Pending._

## Calibration, robustness, behavioural tests

_Pending._

## Limitations known in advance

The 86 behavioural items were written by one person and are small per category: useful as probes,
not as benchmark scores. Their pass rates come with Wilson intervals for that reason.
