# Working in `red-teaming/`

A hobby lab on AI agent security. Stay inside this folder. Other folders in the repo are handled
separately, so never edit them and never rewrite history.

**Work autonomously.** Do not stop to ask questions: make a sensible choice, note it in `PROGRESS.md` and keep
going. The exceptions are steps that need Baris's own accounts, money or competition submissions. Prepare those and
list them under "Needs Baris".

## Ground rules

- Everything runs locally against mocks or against models run on this machine. The harness refuses
  other endpoints in `assert_local`. Do not weaken that.
- Attack examples stay benign: a fake canary token, or a recorded mock call. Addresses use `.test`.
- No working jailbreaks against deployed products, no harmful content, no competition submissions, and
  no automation that talks to an arena or a bounty target.
- Competition breaks stay out of this repo until the disclosure window ends, and even then only as
  classes of weakness. See `arena-notebook/README.md`.
- Do not commit secrets, weights, or datasets. The root `.gitignore` also ignores `data/` and `*.csv`.

## Evaluation rules

These are what make the work worth anything.

- Keep hard and soft defenses apart. A scripted-agent run says nothing about soft defenses.
- A rate needs a denominator, an interval and a note on what it does not cover.
- Trials in one scenario are not independent. Use the cluster bootstrap and scenario-level McNemar.
- A failed or crashed trial stays in the denominator.
- Holdouts are scored once. If you look at the failures and tune, it has become dev data. Write a new one.
- Never report a scripted result as a model result.
- Tests named `..._gap` pin known weaknesses. If one fails, update the write-up, not the test.

## Projects

- `gauntlet/`: `pip install -e ".[dev,llm,agentdojo]"`, then `pytest`. Next is a real model run: `make baseline`.
  After changing a scenario or defense, rerun `make worst-case` and check that the numbers quoted in
  `gauntlet/README.md` and `writeups/README.md` still hold.
- `gauntlet/`, stack search: `make frontier`. Rerun it after changing a hard defense or a scenario, and update
  the numbers in `gauntlet/README.md`, `README.md` and `writeups/dev-scores.md`.
- `tripwire/`: `make test`, then `make fetch experiment robustness final external`. Never train or tune on Gauntlet or
  mcp-lens data. They are the outside test. Report recall and FPR under the same rewrite, together.
- `mcp-lens/`: `pip install -e ".[dev]"`, then `pytest`. Do not add regexes to chase a holdout. Next
  is a semantic review step using a local model, evaluated on a fresh holdout.
- `hermes/`: `make install test experiment`, `make frontier` after changing a control or scenario. Controls are frozen at
  `535f33d` for the benign holdout, which is now spent. `PREREGISTRATION.md` is never edited, only added to. The first
  blind attack-set author was stopped by a safety check: do not retry, reword or re-delegate that content. Baris decides.
- `writeups/`: one section per weakness. Each claim must trace to a report or a test.
- `programs.md`: re-verify dates before relying on them. Sources go in line.

## Environment notes

- `huggingface.co` was blocked in the cloud sandbox used so far, and neither Ollama nor a Docker daemon
  was available there, so model runs need Baris's machine or a sandbox with those allowed.
- Starting third-party npm or PyPI MCP servers was refused in that sandbox, so `mcp-lens/scripts/harvest.py`
  has not been run. Reading installed packages is fine.
- PyPI's torch is a huge GPU build and very slow here. `conda.anaconda.org` is fast: fetch `micromamba` from conda-forge,
  then `micromamba create -n rt -c conda-forge python=3.12 "pytorch=*=cpu_generic*" pip scikit-learn` and
  `-n r r-base r-lme4 r-jsonlite`. Then `pip install -e` the three projects inside `rt`.
- Host denials from the sandbox proxy are policy. Report them in `PROGRESS.md`, do not route around them, and do not fetch
  blocked model weights from re-uploads on package registries.
- Background jobs survive within a run. Two cores: a full `make experiment` plus `make robustness` takes about 30 minutes.

- `artifacts.elastic.co`, `repo1.maven.org` and `docker.elastic.co` are denied too, and there is no Docker daemon, so
  Elasticsearch cannot run here.

Update `PROGRESS.md` at the end of each session.
