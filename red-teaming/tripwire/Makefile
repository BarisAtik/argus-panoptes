PY ?= python

.PHONY: install test fetch experiment robustness report final external

install:
	$(PY) -m pip install -e ".[dev]"

test:
	$(PY) -m pytest

fetch:
	$(PY) scripts/fetch_sources.py

# Three seeds, every split. About 15 minutes on two cores.
experiment:
	$(PY) -W ignore -m tripwire.experiment
	$(PY) -m tripwire.report

# Spelling changes against a fixed threshold. About 25 minutes on two cores.
robustness:
	$(PY) -W ignore -m tripwire.robustness
	$(PY) -m tripwire.report

final:
	$(PY) -W ignore -m tripwire.infer

external:
	$(PY) scripts/external_eval.py
