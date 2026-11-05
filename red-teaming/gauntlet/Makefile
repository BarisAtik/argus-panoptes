PY ?= python
MODEL ?= qwen2.5:7b

.PHONY: install test worst-case agentdojo baseline report

install:
	$(PY) -m pip install -e ".[dev,llm,agentdojo]"

test:
	$(PY) -m pytest

# No model needed. Reproduces reports/worst-case.md.
worst-case:
	gauntlet run --agent compromised --seeds 3 \
	  --defenses none,injection_filter,allowlist,egress,dlp,trifecta,provenance,layered,strict \
	  --ablate layered --out runs/compromised.jsonl
	gauntlet report runs/compromised.jsonl --title "Worst-case architecture run" \
	  --md reports/worst-case.md --json reports/worst-case.json

# No model needed. About 15 minutes on two cores.
agentdojo:
	$(PY) -W ignore -m gauntlet.agentdojo_bridge \
	  --json reports/agentdojo-worst-case.json --md reports/agentdojo-worst-case.md

# First real-model run. Needs a local OpenAI-compatible server (see README).
baseline:
	gauntlet run --agent "openai:$(MODEL)" --seeds 5 \
	  --defenses none,spotlight,prompt_guard,injection_filter,layered,layered-soft \
	  --out runs/$(subst :,-,$(MODEL)).jsonl
	gauntlet report runs/$(subst :,-,$(MODEL)).jsonl --title "Baseline: $(MODEL)" \
	  --md reports/baseline-$(subst :,-,$(MODEL)).md --json reports/baseline-$(subst :,-,$(MODEL)).json

# Blind holdout: score once, see holdout/README.md.
holdout-run:
	gauntlet run --agent compromised --seeds 3 --scenarios holdout \
	  --defenses none,injection_filter,egress,dlp,provenance,layered,strict --out runs/holdout.jsonl
	gauntlet report runs/holdout.jsonl --title "Blind holdout, worst-case agent" \
	  --md reports/holdout.md --json reports/holdout.json

# Decomposition of the frozen stack on the holdout. Descriptive only.
holdout-posthoc:
	gauntlet run --agent compromised --seeds 1 --scenarios holdout --defenses layered --ablate layered \
	  --out runs/holdout-posthoc.jsonl
	gauntlet report runs/holdout-posthoc.jsonl \
	  --title "Blind holdout, post-hoc leave-one-out (not part of the registered scoring)" \
	  --md reports/holdout-posthoc.md --json reports/holdout-posthoc.json

# Predicted tool lists instead of gold ones. No model needed. About 3 minutes on two cores.
router:
	$(PY) -W ignore -m gauntlet.task_router
