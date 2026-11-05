# Validation notes and failure analysis

All numbers below are from `ntl.synth` fake data (seed 7, 2,699 train rows). They show how the
machinery behaves, not how the real competition will go. Fake style signals are clean and fake
prompts share no vocabulary, so several results below are flattering by construction.

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

Intervals resample prompts, not rows, because passages on one prompt are correlated and prompts are
what test samples. Compare models with `paired_prompt_bootstrap`, not by eyeballing a CV gap.

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
- `hf_train.py` has only been run on a tiny random model. It has never trained a real transformer.
- Blend weights are equal. Learn them only with nested CV, or the score will be inflated.
