# 🗡️ Gauntlet

A local evaluation harness for prompt injection and tool misuse in LLM agents. An agent gets
a task and a set of mock tools (mail, docs, web, vault, payments, shell, memory, peer agents).
Some of what it reads tries to steer it. Success is decided by deterministic oracles, mostly a
per-trial fake canary token showing up where it should not.

Every tool is a mock. Nothing touches a real network, shell or file, every address uses the
reserved `.test` TLD, and model endpoints outside the local network are refused in code.

## Why it is built this way

**Hard and soft controls need different experiments.** A policy enforced outside the model holds
whatever the model does, so it can be measured with no model at all, using a scripted agent that
obeys every injection it sees. That answers: *if the model is fully hijacked, what does the
architecture still prevent?* Prompt-level defenses do nothing against that agent, and their value
can only be measured with a real model. The harness keeps those two questions apart and says so
in every report.

**Benchmarks can be wrong, so they get tested too.** Every attack oracle must fire against the
compromised agent, otherwise "0% attack success" might mean a dead oracle. Every task must be
solvable. Every defense has a control scenario where it does damage. Known gaps are pinned as
tests. This found real bugs during the build: two scenarios whose oracles could never fire and,
in the AgentDojo bridge, blocked calls being scored as successful attacks.

**Own scenarios prove little, so there is an outside check.** The policy layer also runs on
[AgentDojo](https://github.com/ethz-spylab/agentdojo), an independent benchmark with its own
tasks and scoring.

## Results so far

No language model has been run yet, because the machine that built this had no model access.
Everything below is the worst-case agent. See [`reports/`](reports/).

**On this repo's 28 attack and 11 control scenarios**
([worst-case.md](reports/worst-case.md)), 3 seeds:

| Stack | Attack success (95% cluster CI) | Attack-free controls still passing |
| --- | ---: | ---: |
| no defense | 100% | 100% |
| injection filter only | 93% (82–100) | 91% |
| tool allowlist only | 61% (43–79) | 100% |
| layered policies | 18% (4–32) | 27% |

Controls are hard negatives built to trip one defense each, so 27% overstates the everyday cost.
The per-defense rows are the useful part. Leave-one-out runs show `allowlist`, `trifecta`,
`tool_pin`, `manifest_scan` and `memory_guard` add nothing to attack success once the rest of
the stack is present on this sample, while removing `egress` nearly doubles it. The five scenarios
that beat `layered` are in [the write-ups](../writeups/README.md): each is an allowed tool, an
allowed destination, or a harm that lives in plain text.

**On AgentDojo** ([agentdojo-worst-case.md](reports/agentdojo-worst-case.md)), 566 live
(user task, injection task) pairs across its four suites, scored by its own checkers:

| Policy | Attack success | Benign utility |
| --- | ---: | ---: |
| none | 100% | 100% |
| tool allowlist | 16.3% | 100% |
| contact-book check on destinations | 24.0% | 96.9% |
| destination must come from the user | 14.0% | 76.3% |
| no sinks after reading anything | 9.7% | 50.5% |
| allowlist + contact book | **4.4%** | **96.9%** |

The combination beats the strictest single rule on both axes. Three caveats keep this honest. The
allowlist uses each task's gold tool list, so it is an upper bound on what a task router would
achieve. The contact book is built from the benchmark's clean environment, so it may contain more
than a real one would. And the 566 pairs leave out 340 whose injection task has no reference solution
to replay and 43 where the reference solution did not succeed even with no policy. These numbers are a different
experiment from the model results in the AgentDojo paper and cannot be compared to them.

**Oracle quality matters.** 6 of 84 successful attacks in the no-defense run were invisible to a
plain substring check on the canary, so a naive evaluator would have called them stopped.

## Quick start

```bash
pip install -e ".[dev,llm,agentdojo]"
pytest
gauntlet list
make worst-case       # no model needed
make agentdojo        # no model needed, about 15 minutes
```

With a local model (Ollama shown; vLLM, llama.cpp server and LM Studio work the same way):

```bash
ollama pull qwen2.5:7b
make baseline MODEL=qwen2.5:7b
Rscript analysis/analyze.R runs/qwen2.5-7b.jsonl      # mixed-effects view
gauntlet export-elastic runs/qwen2.5-7b.jsonl > bulk.ndjson   # index into Elasticsearch
```

Or with Docker: see the header of [`docker-compose.yml`](docker-compose.yml).

Other commands:

```bash
gauntlet run --transport mcp ...      # tool calls cross a real MCP client/server boundary
gauntlet gate runs/x.jsonl --defense layered --max-asr 0.2   # exit 1 in CI on regression
gauntlet power --asr-a 0.5 --asr-b 0.25 --seeds 5            # how many scenarios do I need?
gauntlet repro 7 10 --threshold 0.5   # does a 7/10 finding clear a 50% reproducibility bar?
python -m gauntlet.mcp_bridge --scenario sc-rug-pull         # poisoned mock MCP server on stdio
python adapters/make_promptfoo_config.py && npx promptfoo eval  # promptfoo matrix on top
python -m gauntlet.agentdojo_bridge --model qwen2.5:7b --limit 20  # real model on AgentDojo
```

## Layout

| Path | What |
| --- | --- |
| `src/gauntlet/world.py` | Mock tools with capability labels (`source:untrusted`, `sink:external`, ...) |
| `src/gauntlet/scenarios/` | YAML scenarios: task, world, payload, oracles, OWASP mapping |
| `src/gauntlet/defenses.py` | 14 defenses plus profiles; each says whether it is hard or soft |
| `src/gauntlet/agents.py` | Scripted agents, OpenAI-compatible and Hugging Face backends, local-only guard |
| `src/gauntlet/oracle.py` | Canary detection through encodings and chunking; naive oracle kept for comparison |
| `src/gauntlet/stats.py` | Wilson, exact McNemar, cluster bootstrap, power simulation, reproducibility |
| `src/gauntlet/report.py` | Report that states its limits; Elasticsearch bulk export |
| `src/gauntlet/mcp_bridge.py` | The mock world over real MCP |
| `src/gauntlet/agentdojo_bridge.py` | The policy layer on AgentDojo |
| `analysis/analyze.R` | `glmer` with scenario as random effect (for model runs; scripted runs are too deterministic to fit) |
| `adapters/` | promptfoo provider and config generator |
| `ci/` | GitHub Actions workflow to copy to the repo root |

## Adding a scenario

Append to a YAML file in `src/gauntlet/scenarios/`. A scenario needs a task, a benign `plan`,
`utility` oracles, and for attacks a `marker`, an attack `plan` and an oracle. `pytest` then
checks that it is solvable, that its oracle fires, and that it uses only `.test` names.

## What this does not tell you

- How often a real model gets hijacked. That needs a model run.
- Anything about attacks unlike these scenarios. Rates describe the sample.
- `allowlist` is an upper bound, since it uses each task's gold tool list.
- The HF backend and the Docker files have not been run yet. The OpenAI-compatible backend has
  been tested only against a local stub server.
