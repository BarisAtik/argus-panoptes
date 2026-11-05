# Working in kaggle/

Stay inside this folder. Other folders in the repo have their own owners. Read `PROGRESS.md` first
and update it when you stop.

## Rules

- Never commit competition data, `kaggle.json`, tokens or model weights. `data/`, `artifacts/` and
  `*.csv`/`*.parquet` are ignored.
- Never submit, create accounts or post. Prepare things and list them under "Needs Baris".
- Synthetic scores prove the code runs, nothing more. Always label them as synthetic, and replace
  them when real data arrives.
- Keep the failure analysis honest: record what didn't work, including bugs that fooled you.

## Name That LLM (`name-that-llm/`)

```bash
cd name-that-llm && pip install -r requirements.txt && make test
```

1. If `data/raw/train.csv` is missing, ask Baris to run `scripts/download_data.sh`. Use
   `python -m ntl.synth` until then.
2. On real data, run `ntl.cv --compare-random`, then read the leakage report **before** the scores.
   Check `grid.is_grid` first, since the fold logic and `assign.py` both lean on it.
3. Any new model joins `models.REGISTRY` or writes the same OOF format as `hf_train.write_oof`.
   Keep `grouped_folds` with the default seed, so OOF files stay comparable and can be blended.
4. Compare models with `paired_prompt_bootstrap`. A gap inside the leaderboard noise is not a win.
5. Check the kernel still runs offline: no downloads, 9-hour limit, parquet output.
6. Don't enable `USE_ASSIGNMENT` until the NOTES.md checklist passes.

Don't name the package or a module after a stdlib module, and don't use blanket `sed` over `src/`
without excluding `__pycache__`. Both broke things during setup.

## NFL Big Data Bowl (`nfl-big-data-bowl-2027/`)

1. After download, `python -m combinelink.schema data/raw` lists what doesn't match. Fix
   `schema.py` only. The R script hard-codes `nfl_id`, `game_id`, `lined_up_position` and
   `separation_at_pass_forward`, so update it too if they change.
2. `run.py` pools all drills when it computes reliability and player means. Decide which drills
   are comparable first, then compute per drill.
3. Keep the order: reliability, then transfer, then correction. Don't test metrics that failed the
   first step.
4. The deliverable is a write-up of at most 2,000 words with fewer than 10 figures or tables. Draft
   it early and let it steer the analysis.

## Environment notes

R tooling used here: R 4.4 from conda-forge with tidymodels, glmnet, lme4 and arrow. Set
`PYTHONPATH=src` for anything not run through `make`.
