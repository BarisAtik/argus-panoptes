# Name That LLM

Kaggle code competition: read a 40–250 word passage and name which of 18 frontier models wrote it.
Test prompts are unseen, the metric is balanced accuracy, and scoring runs offline in a notebook.

Why it's fun: it asks whether models have fingerprints that survive a change of topic, and it
punishes sloppy validation in a surprising way (see [NOTES.md](NOTES.md)).

> **Status:** the competition's own data hasn't been seen yet. The pipeline runs end to end on
> synthetic data and on real text from a public stand-in, which tests the validation but says
> nothing about the real leaderboard. Findings so far, on real text: grouped CV landed within 0.010
> of a locked holdout, random CV missed by 0.146, and a change of genre halved the score. A real
> fine-tuned encoder lost to sparse models alone, while the blend of both looks better but missed
> its pre-set bar on one of two splits. Competitors' public reports (self-reported, unverified) put
> this kind of baseline near 0.35 and top scores above 0.7, so the GPU track is where a score
> would come from ([NOTES.md](NOTES.md)).

## Quick start

```bash
pip install -r requirements.txt
make test            # 63 tests; needs torch only for the transformer test, which skips without it
make cv-synth        # grouped CV on fake data, all checks included
make proxy-cv        # the same on real text from public data; no Kaggle account needed

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
| `src/ntl/hf_train.py` | Transformer track: same folds and OOF format, LoRA option, saved folds and offline inference |
| `src/ntl/local_roberta.py`, `transformer_proxy.py`, `transformer_export.py` | Real RoBERTa without Hugging Face, the pre-registered comparison, and predictions for the R audit |
| `src/ntl/labs.py` | The 18 candidate models by lab, for right-lab accuracy in the failure report |
| `src/ntl/proxy.py`, `proxy_experiments.py` | Real-text stand-in in the competition's schema, and the method experiments behind NOTES.md |
| `reports/proxy/` | Raw JSON results of those experiments |
| `kernel/` | Offline submission kernel that fits at run time, plus a GPU training kernel for fold models |
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
Rscript R/04_prompt_effects.R data/raw artifacts/real/oof_blend.parquet  # how clustered are errors?
Rscript R/05_transformer_audit.R artifacts/transformer/predictions.parquet  # needs ntl.transformer_export
```

Packages: tidyverse, tidymodels, glmnet, lme4, arrow.

## Credits

The stand-in uses the Ghostbuster data by Verma et al., CC BY 3.0. It is downloaded at run time and
never committed.
