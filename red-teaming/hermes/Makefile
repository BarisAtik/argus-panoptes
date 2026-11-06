PY ?= python

.PHONY: install test experiment frontier wire

install:
	$(PY) -m pip install -e ".[dev]"

test:
	$(PY) -m pytest

# Seconds. Rewrites reports/experiment.md and .json.
experiment:
	hermes experiment --out reports

# All 4,096 stacks, about 8 minutes on two cores.
frontier:
	hermes frontier --out reports --workers 2

# The surface scenarios over real A2A on loopback TCP.
wire:
	hermes run --wire --stacks none,full
