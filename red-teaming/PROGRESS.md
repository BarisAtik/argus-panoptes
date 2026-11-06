# Progress notes

## 2026-11-05: first run

### Done

- **`gauntlet/`**: local harness with 39 scenarios (28 attacks across 10 weakness categories, 11 controls),
  14 defenses, scripted agents, OpenAI-compatible and Hugging Face backends, real MCP transport, and
  cluster-aware statistics. Reports include their own limits.
- **AgentDojo bridge**: the policy layer on an independent benchmark, scored by its own checkers.
  Worst-case mode ran end to end. Model mode has only met a local stub.
- **`mcp-lens/`**: static scanner for MCP manifests with SARIF output, pinning and an evaluation over
  dev and holdout corpora, plus an optional semantic review step that has not met a real model.
- **`writeups/`**, **`programs.md`**, **`arena-notebook/`**, **`CLAUDE.md`**.
- Tests: `gauntlet` 206 and `mcp-lens` 33, all passing. R analysis checked on synthetic data.

### What the numbers are, and are not

No language model has been run. `huggingface.co` was blocked here and neither Ollama nor a Docker daemon
was available, so every result is the scripted worst-case agent or a synthetic check. They measure
controls, not model behaviour. See the "No language model" banner in each report.

### Not verified

- Dockerfile and compose file (parsed, never built).
- Hugging Face backend (never run). OpenAI-compatible backend (only against a stub).
- promptfoo adapter (provider tested in Python, config generated, promptfoo itself not run).
- `ci/gauntlet.yml.example` (never run, and not active: it has to move to `.github/workflows/`).
- `mcp-lens/scripts/harvest.py` (starting third-party packages was refused in this sandbox).
- garak and PyRIT: used only as text sources for Tripwire, their probes have not been run.

## 2026-11-06: second run, in two sessions

### Done

- **`gauntlet/holdout/`**: blind holdout of 24 attacks and 8 controls. `layered` scored 8.3% ASR and 25% control
  utility. Added `write_scope` and an argument-shape `exec_guard` before freezing.
- **`gauntlet/src/gauntlet/task_router.py`**: real router on AgentDojo. With the contact book, 11.3% ASR and 93.8%
  benign utility, against 4.4% and 96.9% for the gold list. Report in `reports/agentdojo-router.md`.
- **`gauntlet/src/gauntlet/frontier.py`**: all 8,192 hard-defense stacks, Pareto frontier, exact Shapley values,
  picks by fixed rules, scored on the holdout. Report in `reports/frontier.md`.
- **`tripwire/`** finished: complete experiment (36 leave-source-out folds, the earlier file was partial), `report`,
  `evasion`, `robustness`, a GLMM in R on real data, README, frozen final model scored on the Gauntlet and mcp-lens.
- **`writeups/dev-scores.md`**: blog post, ready for Baris to read and post.
- **`programs.md`** refreshed. Wave 3 date conflict settled. Corrected stale `gauntlet/README.md` numbers.
- R and lme4 now installed via conda, so `gauntlet/analysis/analyze.R` ran on a real worst-case file. On
  scripted runs the outcomes are almost deterministic, so that GLMM separates completely (scenario SD near 98)
  and means nothing. Keep it for model runs.

### Not verified

Same list as above, still true: Docker files, Hugging Face backend, promptfoo itself, CI example, `harvest.py`.

### Model access: tried and stopped

`huggingface.co`, `ollama.com`, Docker Hub, `ghcr.io` and `storage.googleapis.com` are denied by the sandbox policy.
The sandbox notes say not to route around such denials, so this run stopped there. An npm search did turn up a third
party's re-upload of TinyLlama weights split across two packages. It was not installed: that would be fetching
blocked content from a mirror, the publisher can't be verified, and TinyLlama has no tool-calling anyway. conda-forge
has `ollama` and `llama.cpp` binaries, but no weights. So still no language model. See "Needs Baris".

## Next, in priority order

1. **Real model baseline.** `make baseline MODEL=qwen2.5:7b`, then a second model. This finally measures
   the soft defenses and everything else here that says "no model". Check the tool-calling tag first. On a CPU this
   is slow. Power simulation: 5 seeds over 40 scenarios gives about 88% power for 50% vs 25%, 20 scenarios about 45%,
   assuming scenario spread of 1 logit. The dev and holdout sets together give 52 attacks, but only use the holdout
   for a frozen comparison.
2. **AgentDojo with a local model**: `python -m gauntlet.agentdojo_bridge --model ... --limit 20`, then full. The 340
   pairs with no reference solution only become testable this way.
3. **Semantic review in mcp-lens**: `python scripts/evaluate.py --semantic MODEL`. `dev2` and `holdout` have never been
   seen by this method, so its first score on them is clean, once.
4. **More controls.** The frontier's cost side rests on 13 and 8 controls, so one scenario moves utility by 8 to 13 points.
   Ordinary benign tasks would also separate "over-fires on hard negatives" from "breaks normal work".
5. **New holdout**, since the current one has now informed two analyses. Have a different author write it.
6. **Fix `pkg_docs` in Tripwire** with a pinned package list, so benign data stops depending on the environment.
7. **Elasticsearch dashboard** over `gauntlet export-elastic`, with the `search/` folder's setup. Needs Docker.
8. **garak or PyRIT probes** against the same local model, for comparison with the scenario set.
9. Move `ci/gauntlet.yml.example` into `.github/workflows/`. That sits outside this folder, so Baris decides.

## Needs Baris

- **Time-sensitive:** Gray Swan IPI Black wave 3 is live until 12 Nov 2026, 10:00 PT, confirmed on
  [the rules page](https://app.grayswan.ai/arena/challenge/ipi-black-2026?panel=rules) on 6 Nov. It needs an account
  and verification, and is entered by hand. Breaks stay private until 30 days after the end. No later AI security
  competition is listed yet, so this is the last prize window for now.
- Create accounts where wanted: Gray Swan Arena, HackerOne, Bugcrowd, 0DIN. Nothing was created or submitted.
- Start on [Proving Ground](https://app.grayswan.ai/arena/challenge/proving-ground), which is free practice.
- **Biggest unlock:** run the model baseline on your own machine, or allow `huggingface.co` for these runs
  (Settings > Capabilities). Everything else in "Next" waits on this.
- Read `writeups/dev-scores.md` and decide whether to post it. It is written in the first person, as you.
- Decide whether to enable the CI workflow, which sits outside this folder.
- Read each program's rules yourself before testing anything real. This lab does not touch real products.

## Earning money: honest notes

Details and sources in [`programs.md`](programs.md). In short:

- **Most realistic:** an invitation to Gray Swan's paid red-teaming work after a track record, or small
  agent security reviews using the Gauntlet report as the sample. Both need time and visibility.
- **Possible, not dependable:** a first bounty of $500 to $5,000 after weeks of practice on agent products,
  where `gauntlet repro` helps with reproducibility bars such as OpenAI's 50%. OpenAI's top tier is reported at
  $100,000, but that is for critical findings and is not a planning number.
- **New, small:** the frontier report is a stronger sample deliverable than the old one, since it tells a client
  what to drop, not only what to add. That helps the agent review idea.
- **Unlikely soon:** competition prizes against a strong field, and a hosted scanner, since free ones exist.
- **Ruled out:** the Anthropic model safety bounty, which means extracting harmful content.

## Log of decisions

- Installed PyTorch and R through conda-forge with micromamba. PyPI's torch is a large GPU build and crawled here.
- Chose canonicalisation over augmentation for the final Tripwire model on third-party data only, before scoring it
  on the Gauntlet. Kept the CNN though TF-IDF matched it, since the project's aim is measurement, and said so.
- Reported that Tripwire stops no more than a regex in the Gauntlet, rather than retuning it on those scenarios.
- Left `allowlist` in the frontier though it uses gold tool lists. Its free-looking Shapley row carries that caveat.
- Fixed the stack-picking rules in the docstring before computing any frontier.
- Used a scripted worst-case agent instead of waiting for a model, because hard controls can be measured
  that way and the result is deterministic.
- Kept fetch tools labelled as sinks. Labelling them read-only would hide query-string exfiltration.
- Froze mcp-lens rules before each holdout, and renamed the used holdout to `dev2` rather than reuse it.
- Left the failed holdout scores in the README instead of tuning them away.
- Did not run third-party MCP packages after that was refused in the sandbox. Used AgentDojo's tool
  definitions as the third-party false-positive set.
