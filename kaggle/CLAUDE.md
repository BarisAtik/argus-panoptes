# Working in kaggle/

Stay inside this folder. Other folders in the repo have their own owners. Read `PROGRESS.md` first
and update it when you stop.

## How to work

Work autonomously. Don't stop to ask questions: make a sensible choice, record it in `PROGRESS.md`,
and keep going. The only exceptions are steps that need Baris's own accounts, money or competition
submissions. Prepare those and list them under "Needs Baris".

## Rules

- Never commit competition data, `kaggle.json`, tokens or model weights. `data/`, `artifacts/` and
  `*.csv`/`*.parquet` are ignored.
- Never submit, create accounts or post. Prepare things and list them under "Needs Baris".
- Synthetic scores prove the code runs, nothing more. Always label them as synthetic, and replace
  them when real data arrives. Proxy scores test the method, not the leaderboard, so label those
  too.
- This is a personal hobby lab, and everything committed should read that way.
- Keep the failure analysis honest: record what didn't work, including bugs that fooled you.

## Name That LLM (`name-that-llm/`)

```bash
cd name-that-llm && pip install -r requirements.txt && make test
```

0. Read NOTES.md Part 0 first. Public reports put linear models near 0.35 and fine-tuned LLMs above
   0.6, so the GPU track (`kernel/train_gpu_kernel.py`, then `FOLDS_DIR` in the submission kernel)
   now matters more than further tuning of sparse models. Those reports are unverified leads.
1. If `data/raw/train.csv` is missing, Baris still has to run `scripts/download_data.sh`. Until
   then use `make proxy-cv` (real text, public data), or `python -m ntl.synth` for quick checks.
2. On real data, run `ntl.cv --compare-random`, then read the leakage report **before** the scores.
   Check `grid.is_grid` first, since the fold logic and `assign.py` both lean on it.
3. Any new model joins `models.REGISTRY` or writes the same OOF format as `hf_train.write_oof`.
   Keep `grouped_folds` with the default seed, so OOF files stay comparable and can be blended.
4. Compare models with `paired_prompt_bootstrap`, across repeated splits. A gap inside the
   leaderboard noise is not a win. On one proxy split the eventual winner ranked below plain TF-IDF on OOF.
5. Check the kernel still runs offline: no downloads, 9-hour limit, parquet output.
6. Leave `USE_ASSIGNMENT` off. Test prompts reportedly hold 1–8 passages, and the proxy lost score
   the same way. Read the adversarial AUC in the kernel log first: on the proxy, a genre change took
   it to 0.99 and halved the score, and grouped CV didn't notice. `USE_BALANCE` is the switch to try if that happens.

7. Test is hidden until the scoring rerun, so transformer test predictions must come from
   `predict_folds` inside the submission kernel. Blend weights come from nested CV on OOF files.
8. Before using any external text pool, find its source, labels and licence, and check the rules.

Don't name the package or a module after a stdlib module, and don't use blanket `sed` over `src/`
without excluding `__pycache__`. Both broke things during setup.

## NFL Big Data Bowl (`nfl-big-data-bowl-2027/`)

0. The real analysis is `python -m combinelink.run --by-drill`. Run the mixed model in R afterwards.
1. After download, `python -m combinelink.schema data/raw` lists what doesn't match. Fix
   `schema.py` only. The R script hard-codes `nfl_id`, `game_id`, `lined_up_position` and
   `separation_at_pass_forward`, so update it too if they change.
2. Plain `analyse` pools all drills, so use it only as a sanity check. `analyse_by_drill` is the
   planned analysis. Check the reliability cut-off of 0.7 before seeing any outcome.
3. Keep the order: reliability, then transfer, then correction. Don't test metrics that failed the
   first step.
4. The deliverable is a write-up of at most 2,000 words with fewer than 10 figures or tables. Draft
   it early and let it steer the analysis.
5. `combinelink.public_proxy` has only run on fake tables. Don't run it on the real nflverse tables
   unless Baris has said so in `PROGRESS.md`: they carry no data licence. If he has, follow
   `reports/public_proxy_plan.md` unchanged and report every planned test.

## Environment notes

R tooling used here: R 4.4 from conda-forge with tidymodels, glmnet, lme4 and arrow. Set
`PYTHONPATH=src` for anything not run through `make`.

In cloud sessions, kaggle.com, Hugging Face, CRAN and arXiv may be unreachable. PyPI, conda-forge,
GitHub releases and raw.githubusercontent.com worked. Get R with micromamba from conda.anaconda.org.
Torch comes from PyPI, since download.pytorch.org is blocked.

No Hugging Face? `ntl.local_roberta` rebuilds a real RoBERTa from spaCy's wheel. CPU fine-tuning runs
at about one passage per second on 2 cores, so plan experiments around that, and use
`transformer_proxy`'s caching. Fetch the proxy with at most 6 workers. A proxy that drops connections
once left a partial cache that looked like a very easy dataset: a loss of 0.3 after ten steps was the
clue, and `make_split` now refuses partial caches.

Check a dataset's licence before analysing it, not after downloading it.
