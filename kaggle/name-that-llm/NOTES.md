# Validation notes and failure analysis

This file has two parts. The first uses real text from a public stand-in. The second uses fake data
and is kept for its reasoning, with corrections marked where real text disagreed.

## Part 1: real text from a public stand-in

The competition data still hasn't been seen, so these are **not forecasts of a leaderboard score**.
`ntl.proxy` cuts the public [Ghostbuster data](https://github.com/vivek3141/ghostbuster-data)
(CC BY 3.0, [Verma et al.](https://arxiv.org/abs/2305.15047)) to the competition's shape: 1,000
essay prompts and 1,000 story prompts, each answered by a human, Claude and five GPT variants. Passages
are cut to a random 40–250 words, independently of author. Most runs use 150 train prompts and 220
locked test prompts, in the competition's schema.

Differences from the real thing: 7 authors rather than 18, models from 2023, and two genres. The GPT
folders aren't documented in the data's README, so I treat them as sibling configurations of one
model. That makes them a hard version of sibling confusion, but not the same thing as sibling models.

Raw results are in `reports/proxy/*.json`. Reproduce with `make proxy-experiments`.

### Grouped CV predicts a locked holdout. Random CV doesn't

Ten resampled splits, TF-IDF model:

| Estimate | Mean score | Mean error against holdout |
| --- | --- | --- |
| Grouped by prompt | 0.490 | 0.010 |
| Random folds | 0.345 | 0.146 |
| Locked holdout | 0.491 | |

The odd direction from Part 2 is real: random folds **under**report here too, and by far more than
any model change below. The prompt-bootstrap CI contained the holdout score 10 times out of 10. Its
half-width is about 0.025 while the observed gap has SD 0.0125, so it is conservative.

### Correction: prompts were not correlated the way I assumed

Part 2 justifies the prompt bootstrap by saying passages on one prompt are correlated. On real text
the binomial mixed model in `R/04_prompt_effects.R` put prompt variance at zero (singular fit), and
prompt-level accuracy was slightly *less* spread out than binomial (SD 0.169 against 0.189). That
fits a grid: every prompt has the same mix of easy and hard authors, which evens prompts out.

The bootstrap stays, because prompts are still what test samples and it is the safer choice. Check
again on real data before repeating the correlation argument.

### Choosing models

| Candidate | OOF | Holdout | Holdout minus TF-IDF, 95% CI | Author family accuracy |
| --- | --- | --- | --- | --- |
| Blend: TF-IDF, masked, style | 0.493 | 0.529 | +0.041 (0.020, 0.063) | 0.896 |
| Blend: TF-IDF, masked | 0.501 | 0.515 | +0.027 (0.008, 0.044) | 0.893 |
| TF-IDF, weaker regularisation | 0.511 | 0.488 | 0.000 (−0.006, 0.006) | 0.877 |
| TF-IDF | 0.506 | 0.488 | | 0.877 |
| Family first, then author | 0.510 | 0.484 | −0.003 (−0.013, 0.006) | 0.864 |
| Word n-grams | 0.511 | 0.464 | −0.024 (−0.040, −0.007) | 0.849 |
| Masked text | 0.477 | 0.469 | −0.019 (−0.042, 0.002) | 0.866 |
| Style only | 0.344 | 0.375 | −0.113 (−0.141, −0.087) | 0.758 |

That is one split, and it is a trap: the blend ranks low on OOF and first on holdout. Repeating it
over six splits shows seed 0 was noise, not a pattern:

| Candidate | Mean OOF | Mean holdout |
| --- | --- | --- |
| TF-IDF + masked | 0.498 | 0.506 |
| All three | 0.498 | 0.508 |
| TF-IDF | 0.490 | 0.494 |

- Blending with masked text helped on all six holdouts, by about 0.012. Picking on OOF cost 0.009
  on average against the best candidate in hindsight, a small price.
- Style adds nothing measurable on top. Fake data had blends winning by far more, and masked text
  beating raw TF-IDF, which real text reversed.
- The hierarchical model from the old to-do list did not help, so it is off the list unless real
  sibling structure says otherwise.
- **Lesson:** a gap of 0.02 between candidates on one split means little here. Compare across
  resampled splits, which the real competition's 150 prompts allow through repeated grouped CV.

### Where it fails

Author family accuracy is 0.88 and author accuracy 0.49, so nearly all the error is among siblings.
Claude and human recall sit near 0.75, the five GPT variants at 0.34–0.47.

Passage length barely mattered, unlike the fake data. The mixed model's length effect is −0.04
(SE 0.07), and the longest bin was the worst, 0.43 against 0.46–0.55. I can't explain that bin yet.

Essays are harder than stories (log-odds difference 0.46, SE 0.14). The blend is underconfident:
passages at 0.65 confidence were right 91% of the time. That is expected from a geometric mean, and
it matters only if something downstream trusts the probabilities.

Which style features are about the author? From `R/01`, colons (18% of variance) and commas (11%)
beat prompt share or come close, while word length is 65% prompt. Hand-written style features alone
give 0.34 in both R and Python, and random folds don't hurt them (0.348 against 0.337), which
supports the topic explanation in Part 2.

### What more data is worth

Holdout score against training prompts, mean of two splits, 7 authors:

| Train prompts | 38 | 75 | 150 | 300 | 600 | 1,200 |
| --- | --- | --- | --- | --- | --- | --- |
| Holdout | 0.422 | 0.466 | 0.495 | 0.533 | 0.554 | 0.565 |

Doubling from 150 prompts adds about 0.04, more than any model change above. So if the competition
allows generated training data, that may be the best lever. As of the last public report that
question was **unanswered on the forum**. Don't use it until it's settled.

### The big risk: grouped CV can't see a change of genre

Trained on 150 prompts of one genre:

| Train | Model | Grouped CV | Unseen, same genre | Unseen, other genre |
| --- | --- | --- | --- | --- |
| Stories | TF-IDF | 0.543 | 0.547 | **0.244** |
| Essays | TF-IDF | 0.540 | 0.539 | **0.163** |
| Stories | Masked | 0.499 | 0.515 | **0.246** |
| Essays | Masked | 0.505 | 0.509 | **0.192** |
| Stories | Style | 0.425 | 0.424 | **0.145** |
| Essays | Style | 0.425 | 0.421 | **0.111** |

Chance is 0.143. Grouped CV matched same-genre holdouts almost exactly and said nothing about the
other genre. Masking didn't rescue it, so "style transfers across topics" is false here. Train
genres being mixed protects you only against genres that are in train.

What helps and what warns:

- **Adversarial validation warns clearly:** AUC 0.50–0.55 on the same genre, 0.996–0.999 on the
  other. It sits in the kernel log, so read it after the first run.
- **Topic-held-out folds (`--topic-folds`) warn weakly.** On mixed data they gave 0.507, 0.444 and
  0.473 against grouped 0.506, 0.476 and 0.488. They didn't reach the size of a true genre shift.
- **Unlabelled fixes recover little.** Evening out class shares took essays→stories from 0.163 to
  0.224, and stories→essays from 0.244 to 0.249. Scaling style features by test's own statistics
  took style from 0.111 to 0.193 and 0.145 to 0.197. None gets close to same-genre scores.

### Evening out class shares: keep it off unless shift shows up

`balance_classes` adds 0.003 on the mixed split (one of five CIs clears zero) and costs 0.007 if test
is really unbalanced, so it is off by default. It is a reasonable switch only if adversarial AUC
fires, since it helped under shift and rarely hurt otherwise.

### Within-prompt assignment: the checklist did its job

| Split | Clustering ARI | Argmax | Assigned | Oracle prompts |
| --- | --- | --- | --- | --- |
| 0 | 0.56 | 0.488 | 0.494 | 0.606 |
| 1 | 0.60 | 0.490 | 0.490 | 0.582 |
| 2 | 0.62 | 0.487 | 0.518 | 0.571 |

Fake prompts clustered perfectly (ARI 1.0). Real ones reach about 0.6, far from the checklist's 0.9.
Real assignment gains 0.012 on average, while a perfect clustering would gain about 0.10. So the
prize is real and the clustering is the blocker, and only one of three CIs clears zero. It rarely
hurt here, which is milder than the stress table in Part 2 suggested.

Trusting only clusters of exactly full size failed: only 3–18% of rows land in one, and the score
changed by −0.002 on average.

### Leaderboard noise, redone on real predictions

Public-minus-private gap: SD 0.028, 95th percentile 0.057, at the proxy's 150 prompts and 7 authors.
That is about twice the fake data's value. Real test has more prompts, so recompute it there.

## Part 2: fake-data reasoning

Numbers here are from `ntl.synth` (seed 7, 2,699 train rows). They show how the machinery behaves,
not how the real competition will go. Fake style signals are clean and fake prompts share no
vocabulary, so several results below are flattering by construction.

## The structural fact

2,699 rows over 150 prompts and 18 models is 149.9 × 18. Train looks like a nearly complete
prompt × model grid: every model answered every prompt. `grid_report` measures this on real data
rather than assuming it. It has two consequences.

## Why folds must keep prompts whole, and the surprise in which way random folds fail

Test prompts are unseen, so the honest scheme is `StratifiedGroupKFold` on `prompt_id`.

Usually a split like this stops scores being too *high*. On a grid, random folds can go the other
way:

| Scheme | Features | Balanced accuracy |
| --- | --- | --- |
| Grouped by prompt | TF-IDF | 0.662 |
| Random k-fold | TF-IDF | **0.139** |
| Grouped by prompt | Style only (R) | 0.453 |
| Random k-fold | Style only (R) | 0.452 |

The most likely explanation: with random folds, a held-out passage's prompt is in train, written
by every model except a few, including its real author. The model learns "this topic goes with
those 14 models", which pushes down the correct answer. The style-only row supports this: no topic
features, no effect. Expect the real
gap to be smaller, because fake topics are perfectly separated. Whichever way it goes on real data,
a random-fold score is not an estimate of test performance.

## What the leakage checks are for

| Check | Failure it catches |
| --- | --- |
| Grid report | The fold and assignment logic resting on a false assumption |
| Duplicates | One passage under two labels, or one crossing prompts |
| Identity mentions | Passages naming their own model ("as an AI made by…"), which may not hold in test |
| Row order and id signal | Files sorted by label |
| Length η² | Passages cut differently per model |
| Adversarial validation | Style drift between train and test |
| Test-to-train similarity | The claim that test prompts are unseen |
| Test cluster shape | Whether test is a grid too |

Two bugs found while building these are worth remembering, and both now have regression tests:

- **Duplicate check reported every row as a duplicate.** With no real duplicates the filtered frame
  was empty, and `.assign()` on an empty frame adopts the assigned Series' index. It brought all
  2,699 rows back with empty text.
- **Adversarial AUC was 0.99 between train and test from the same generator.** Test passages shared
  prompts across the split, so the model recognised topics. Grouping test by recovered prompt and
  masking content words brought it to 0.50. An alarm that always rings is worse than none.

## Candidates

| Model | Balanced accuracy | 95% CI (prompt bootstrap) |
| --- | --- | --- |
| Blend (geometric mean) | 0.799 | 0.785–0.813 |
| Masked text LR | 0.764 | 0.747–0.779 |
| TF-IDF LR | 0.662 | 0.647–0.679 |
| Style features LR | 0.531 | 0.514–0.548 |

R recomputed the blend from the OOF file independently and got the same 0.7988, with CI
0.785–0.813. Masked beating raw TF-IDF is partly an artefact: fake topic words are pure noise. Don't
assume it on real text.

Intervals resample prompts, not rows, because prompts are what test samples. (This also claimed
passages on one prompt are correlated. Real text didn't support that; see Part 1.) Compare models with `paired_prompt_bootstrap`, not by eyeballing a CV gap.

**Leaderboard noise.** With a 40/60 public/private split by prompt, the same predictions gave a
public-minus-private gap with SD 0.015 and 95th percentile 0.031. A public improvement smaller than
that is noise. Recompute on real OOF predictions before reading anything into the leaderboard.

## Within-prompt assignment: large gain, narrow margin

If test is also a grid, passages on one prompt have different authors. `assign.py` recovers prompts
by clustering, then solves an assignment problem inside each cluster.

| Share of rows mis-clustered | All rows kept | 70% of rows kept | Argmax baseline |
| --- | --- | --- | --- |
| 0% | **0.896** | 0.849 | 0.799 / 0.797 |
| 10% | 0.813 | 0.786 | |
| 25% | 0.755 | 0.733 | |
| 50% | 0.729 | 0.692 | |

The gain is about +0.10 with perfect clusters, but it is close to gone at 10% noise and harmful by
25%. Noise here is random, which is the worst case, and real mistakes will cluster among similar
prompts. Real prompts also overlap in topic, unlike the fake ones (ARI 1.0).

This uses test text jointly but no labels. That is transductive inference, not hand labelling, but
read the rules and forum on it before relying on it.

**Off by default.** Turn it on only if all of these hold:

1. `grid.is_grid` is true on real train.
2. `test_cluster_shape.share_rows_in_full_clusters` in the kernel log shows sizes piling up at 18.
3. Clustering all of train at the tuned threshold gives ARI above about 0.9.
4. `paired_vs_argmax` has a lower bound above 0 on real OOF predictions.
5. A submission with it beats one without by more than the leaderboard noise above.

Train is 2,699 rows and test about 4,000, so clustering will be harder on test than this check
suggests.

## Failure analysis so far

From `ntl.failure` on the fake blend: the worst recall is 0.667, the top confusions are all siblings
from one lab, and accuracy climbs with passage length (0.649 under 80 words). The sibling pattern is
built into the generator, but it's the first thing to check on real data, along with:

- the gap between lab-level and model-level accuracy, once `lab_of` is filled in for the real names;
- which real models are near-duplicates, and whether any are effectively unseparable;
- whether short passages need a different model;
- whether calibration holds, since the blend and assignment both trust the probabilities.

## Known limits

- The schema comes from a third-party write-up of the competition, not the data itself. `data.py`
  fails loudly if columns differ.
- `style_lr` and R's style features overlap but are not identical, so compare metrics across
  languages, not feature values.
- `hf_train.py` has only been run on a tiny random model. It has never trained a real transformer,
  so every Part 1 result is about sparse linear models. A transformer may change the rankings.
- Part 1's holdouts were looked at more than once, so treat the small gaps there as rough.
- Blend weights are equal. Learn them only with nested CV, or the score will be inflated.
