PY ?= python
export PYTHONPATH := src
.PHONY: test lint synth cv submit-synth failure r-all

test:
	$(PY) -m pytest -q
lint:
	$(PY) -m ruff check src tests kernel
synth:
	$(PY) -m ntl.synth --out data/synth
cv: ## grouped CV on real data
	$(PY) -m ntl.cv --data data/raw --out artifacts/real --compare-random
cv-synth: synth
	$(PY) -m ntl.cv --data data/synth --out artifacts/synth --compare-random
submit-synth: synth
	$(PY) -m ntl.submit --data data/synth --out artifacts/synth/submission.parquet
failure:
	$(PY) -m ntl.failure --oof artifacts/synth/oof_blend.parquet --data data/synth
r-all:
	Rscript R/01_eda_stylometry.R data/synth
	Rscript R/02_tidymodels_grouped_cv.R data/synth
