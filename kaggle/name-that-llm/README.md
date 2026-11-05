# Name That LLM

Kaggle code competition: read a 40–250 word passage and name which of 18 frontier models wrote it.
Test prompts are unseen, the metric is balanced accuracy, and scoring runs offline in a notebook.

Why it's fun: it asks whether models have fingerprints that survive a change of topic, and it
punishes sloppy validation in a surprising way (see [NOTES.md](NOTES.md)).

> **Status:** the pipeline runs end to end, but only on **synthetic data** so far. No score here
> says anything about the real competition. First task with real data: rerun everything and replace
> the numbers in NOTES.md.

## Quick start

```bash
pip install -r requirements.txt
make test            # 45 tests; needs torch only for the transformer test, which skips without it
make cv-synth        # grouped CV on fake data, all checks included

./scripts/download_data.sh        # your Kaggle credentials; accept the rules on the site first
PYTHONPATH=src python -m ntl.cv --data data/raw --out artifacts/real --compare-random
PYTHONPATH=src python -m ntl.failure --oof artifacts/real/oof_blend.parquet --data data/raw
```

## Layout

| Path | What it does |
| --- | --- |
| `src/ntl/data.py` | Schema checks, plus the prompt × model grid report that drives the validation design |
| `src/ntl/splits.py` | Stratified group folds on `prompt_id`, with an overlap assertion |
| `src/ntl/leakage.py` | Duplicates, self-naming, row-order signal, length, adversarial validation, unseen-prompt and test-grid checks |
| `src/ntl/features.py`, `models.py` | Word/char TF-IDF, content-masked text, 23 named style features |
| `src/ntl/cv.py` | OOF predictions, blend, prompt-bootstrap CIs, leaderboard-noise simulation |
| `src/ntl/assign.py` | Optional: recover hidden test prompts, then give each model one passage per prompt |
| `src/ntl/failure.py` | Confusions, accuracy by length, calibration, hardest prompts |
| `src/ntl/submit.py` | Fit on all of train, write and validate `submission.parquet` |
| `src/ntl/hf_train.py` | Transformer track with the same folds and OOF format |
| `kernel/` | Offline Kaggle script that fits at run time, so no pickle is tied to a library version |
| `R/` | Variance decomposition (lme4), tidymodels grouped CV, independent audit of Python's OOF scores |
| `Dockerfile` | CPU environment for the baseline. Written but not yet built |

## Submitting

You do this part; nothing in the repo submits for you.

```bash
./scripts/package_source.sh YOUR_KAGGLE_USERNAME   # prints the two kaggle commands to run
```

Then submit the kernel's `submission.parquet` from the competition page. The limit is 5 per day,
and 2 final picks. Choose finals from CV, not from the public leaderboard.

## R

```bash
Rscript R/01_eda_stylometry.R data/raw            # who wrote it vs what was asked
Rscript R/02_tidymodels_grouped_cv.R data/raw     # interpretable multinomial model
Rscript R/03_oof_audit.R artifacts/real/oof_blend.parquet
```

Packages: tidyverse, tidymodels, glmnet, lme4, arrow.
