# Working in models/ (the Forge)

Public hobby lab. Python package `argus-forge`, installed from this folder with
`pip install -e ".[dev,asr,text,vision]"`. Read `PROGRESS.md` first: the TODO there is the plan.

## Working style

Work autonomously: make a sensible choice, note it in `PROGRESS.md`, and keep going without
stopping to ask. The exceptions are steps that need Baris's own accounts, money or competition
submissions. List those under "Needs Baris" instead.

Network limits are not obstacles to route around. If a host or repository is refused, use what
this session may reach, and record what is needed. A download that works through a gap in
enforcement doesn't count as permission.

## Commands

- `pytest` runs all tests (no network, no GPU). `pytest -m "not torch"` skips the tiny-model ones.
- `ruff check .` must pass. Line length 100.
- Before committing, both must pass.

## Layout

- `forge/`: framework-free stats, calibration, retrieval metrics, reports. Reuse it. Don't
  reimplement a metric inside a project.
- `asr_nl/`, `text_nl/`, `clip_search/`: one package per project. Each has a README and an
  evaluation card (`text_nl/MODEL_CARD.md`, `*/EVALUATION_CARD.md`).
- `scripts/first_results.sh`: first real runs, in order of effort (`text`, `clip`, `asr`).
- `tests/`: one file per project. Heavy imports (torch, transformers) stay inside functions so
  that the shared code imports without them.
- `runs/`: gitignored, for all generated output. `results/<project>/`: curated, committed reports.

## Getting models in a locked-down session

Package registries work where model hubs don't. From conda-forge (`conda.anaconda.org`):
`spacy-model-nl_core_news_{sm,md,lg}` and `nltk_data` (holds `corpora/conll2002`). A `.conda` file
is a zip holding a zstd tar: unpack, then copy `site-packages/*` into the venv. Or take
`micromamba` from the same channel and solve one environment, which also brings PyTorch CPU and R.
Check the licence of whatever comes this way. Third-party re-uploads of weights from a blocked hub
are not package installs: leave those alone until Baris decides.

## Rules that keep this honest

- Never write a performance number in a README or card unless it comes from a `real` report in
  `results/`. Quote it with its interval, its date and the commit it came from.
- A `smoke` report is not a result. Tiny models exist only to run the code path.
- Add hypotheses to the evaluation card and commit them before running the experiment. Keep
  hypotheses that turned out wrong, and mark them so.
- If a real run contradicts the code's assumptions (a column name, an archive layout), fix the
  code and add a test with that real shape.
- Fit anything tuned (temperature, thresholds) on validation data only.

## How to continue each project

**asr_nl.** Get data with `asr_nl.fetch_common_voice` (needs `MDC_API_KEY`), run
`asr_nl/configs/laptop.yaml`, read the audit first. The first real run will test
`from_common_voice_tsv` against the current archive layout, so look there if parsing fails.
Common Voice accents are free text: they likely need a mapping table before slices mean anything.
Then run `full_gpu.yaml` and fill in `asr_nl/EVALUATION_CARD.md`. The `sherpa-*` backends run ONNX
exports on CPU; add Parakeet this way for hypothesis 7. Slices use the cluster t interval on
purpose (`docs/small_group_coverage.md`).

**text_nl.** Start with `--baseline-only`, read the audit (leak share!), then fine-tune. Compare
`--truncation head` with `head_tail`, over at least 3 seeds. Review `suspicious_labels.json` by
hand and record what share is truly mislabeled. Fill in `text_nl/MODEL_CARD.md`.

**clip_search.** `python -m clip_search.coco`, then `clip_search.cli` with both default models.
Then build a demo index and try `clip_search.app`. The `es_export` output is meant for the
Elasticsearch experiments in the sibling `search/` folder; leave that folder to its own sessions.

**pii_nl.** `test` and `test2` are spent: read them freely, but they no longer count as blind. Any
new claim needs a new blind set from a fresh agent that can't see `rules.py`, committed with its
hypotheses before scoring. Check `pytest` passes before a freeze: a skipped check cost a clean
result here. The next real step is real documents with consent, or public ones (see `PROGRESS.md`).

**ner_nl.** Run stages in the order listed at the top of `ner_nl/run.py`, or `scripts/ner_study.sh`,
in the environment from `ner_nl/environment.yml` (DEDUCE's `regex` pin clashes with `transformers`).
CoNLL-2002 is local only. Sentences must not reach the repo, including in review notes. Record
verdicts by position. Models trained on it are never hosted or sold. Before quoting the name gap,
do the per-name analysis in `PROGRESS.md`: twenty surnames per list is thin. `run.py` needs the
own-model runs before `evaluate`. A new backend goes in `backends.py` and gets all three tests.

## Git

Overnight sessions own only `models/`. Commit with a clear message and pull with rebase before
pushing. Other sessions push to the same branch. Never rewrite history.
