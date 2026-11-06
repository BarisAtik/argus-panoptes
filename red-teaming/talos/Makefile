PY ?= python
RSCRIPT ?= Rscript

.PHONY: install test study study2 report serve

install:
	$(PY) -m pip install -e ".[dev]"

test:
	$(PY) -m pytest

# 60 models. About two hours on two CPU cores. Finished models are skipped, so it can be restarted.
study:
	$(PY) -m talos.study --out data/runs --jobs 2

report:
	$(PY) -m talos.report
	$(RSCRIPT) analysis/talos.R data/all.csv.gz > data/glmm.txt
	$(PY) -m talos.report

# Second study, named senders. 16 models, about 40 minutes on two cores.
study2:
	$(PY) -m talos.study2
	$(PY) -m talos.study2 --report

# One trained model behind an OpenAI-style endpoint on loopback.
serve:
	$(PY) -m talos.serve $(MODEL)
