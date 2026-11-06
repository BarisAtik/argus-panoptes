PY ?= python

.PHONY: install test experiment inference frontier wire holdout2

install:
	$(PY) -m pip install -e ".[dev]"

test:
	$(PY) -m pytest

# Seconds. Rewrites reports/experiment.md and .json.
experiment:
	hermes experiment --out reports

# Seconds. Rewrites reports/inference.md and .json. Needs reports/experiment.json to compare old stacks against.
inference:
	$(PY) -m hermes.cli inference --out reports

# All 4,096 stacks, about 8 minutes on two cores.
frontier:
	hermes frontier --out reports --workers 2

# The surface scenarios over real A2A on loopback TCP.
wire:
	hermes run --wire --stacks none,full

# The second blind benign holdout. Scored once: refuses to overwrite reports/holdout2.*.
HOLDOUT2 ?= holdout/06_blind_controls_2.yaml
holdout2:
	$(PY) -m hermes.cli holdout2 --path $(HOLDOUT2) --out reports

# Hop attenuation against a local model: make hops MODEL=qwen2.5:7b
BASE_URL ?= http://localhost:11434/v1
hops:
	$(PY) -m hermes.hops --model $(MODEL) --base-url $(BASE_URL) --out reports/hops-$(subst :,-,$(subst /,-,$(MODEL)))
