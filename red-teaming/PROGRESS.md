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
- garak and PyRIT: not integrated. AgentDojo and promptfoo took priority.

## Next, in priority order

1. **Real model baseline.** `make baseline MODEL=qwen2.5:7b`, then a second model. This finally measures
   the soft defenses. Check the tool-calling tag on Ollama first. Budget: on a CPU this will be slow.
   Power simulation says 5 seeds over 40 scenarios gives about 88% power to detect 50% vs 25%, and 20
   scenarios only about 45%, assuming scenario spread of 1 logit. So grow the set to 40+ attacks first
   if comparing two soft defenses.
2. **Grow scenarios to 40+ attacks**, ideally with someone else writing some, since one author wrote both
   payloads and defenses. Add a `write_scope` defense for file paths and argument-level exec rules, which
   would close two of the five residual scenarios.
3. **AgentDojo with a local model**: `python -m gauntlet.agentdojo_bridge --model ... --limit 20`, then
   full. The 340 pairs with no reference solution only become testable this way.
4. **Semantic review in mcp-lens**: `python scripts/evaluate.py --semantic MODEL`. `dev2` and `holdout`
   have never been seen by this method, so its first score on them is clean, once.
5. **Wider false-positive check**: run `harvest.py` in a throwaway container.
6. **A blog post** on "100% on dev, 5% on holdout". It is the most shareable result here.
7. **Realistic task router** to replace the gold `allowlist`, then report the gap to the upper bound.
8. **Elasticsearch dashboard** over `gauntlet export-elastic`, perhaps with the `search/` folder's setup.
9. **garak or PyRIT** probes against the same local model, for a comparison with the scenario set.
10. Move `ci/gauntlet.yml.example` into `.github/workflows/`.

## Needs Baris

- **Time-sensitive:** Gray Swan IPI Black wave 3 is listed as live until 12 Nov 2026, 10:00 PT. Sources disagree
  on dates, so check [the rules page](https://app.grayswan.ai/arena/challenge/ipi-black-2026?panel=rules).
  Requires an account and verification, entered by hand. Breaks stay private until 30 days after the end.
- Create accounts where wanted: Gray Swan Arena, HackerOne, Bugcrowd, 0DIN. Nothing was created or submitted.
- Start on [Proving Ground](https://app.grayswan.ai/arena/challenge/proving-ground), which is free practice.
- Run the model baseline on your own machine, or allow `huggingface.co` for these runs (Settings > Capabilities).
- Decide whether to enable the CI workflow, which sits outside this folder.
- Read each program's rules yourself before testing anything real. This lab does not touch real products.

## Earning money: honest notes

Details and sources in [`programs.md`](programs.md). In short:

- **Most realistic:** an invitation to Gray Swan's paid red-teaming work after a track record, or small
  agent security reviews using the Gauntlet report as the sample. Both need time and visibility.
- **Possible, not dependable:** a first bounty of $500 to $5,000 after weeks of practice on agent products,
  where `gauntlet repro` helps with reproducibility bars such as OpenAI's 50%.
- **Unlikely soon:** competition prizes against a strong field, and a hosted scanner, since free ones exist.
- **Ruled out:** the Anthropic model safety bounty, which means extracting harmful content.

## Log of decisions

- Used a scripted worst-case agent instead of waiting for a model, because hard controls can be measured
  that way and the result is deterministic.
- Kept fetch tools labelled as sinks. Labelling them read-only would hide query-string exfiltration.
- Froze mcp-lens rules before each holdout, and renamed the used holdout to `dev2` rather than reuse it.
- Left the failed holdout scores in the README instead of tuning them away.
- Did not run third-party MCP packages after that was refused in the sandbox. Used AgentDojo's tool
  definitions as the third-party false-positive set.
