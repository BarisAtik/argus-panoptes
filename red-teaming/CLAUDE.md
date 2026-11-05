# Working in `red-teaming/`

A hobby lab on AI agent security. Stay inside this folder. Other folders in the repo are handled
separately, so never edit them and never rewrite history.

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
- `mcp-lens/`: `pip install -e ".[dev]"`, then `pytest`. Do not add regexes to chase a holdout. Next
  is a semantic review step using a local model, evaluated on a fresh holdout.
- `writeups/`: one section per weakness. Each claim must trace to a report or a test.
- `programs.md`: re-verify dates before relying on them. Sources go in line.

## Environment notes

- `huggingface.co` was blocked in the cloud sandbox used so far, and neither Ollama nor a Docker daemon
  was available there, so model runs need Baris's machine or a sandbox with those allowed.
- Starting third-party npm or PyPI MCP servers was refused in that sandbox, so `mcp-lens/scripts/harvest.py`
  has not been run. Reading installed packages is fine.
- `apt-get update` is needed before `apt-get install r-base-core r-cran-lme4 r-cran-jsonlite`.

Update `PROGRESS.md` at the end of each session.
