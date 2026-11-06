PY ?= python
export PYTHONPATH := src
.PHONY: test lint synth cv submit-synth failure r-all proxy proxy-cv proxy-experiments

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
proxy: ## download the public real-text stand-in and cut it to competition size
	$(PY) -m ntl.proxy download --cache data/proxy/cache
	$(PY) -m ntl.proxy build --cache data/proxy/cache --out data/proxy/comp
proxy-cv: proxy
	$(PY) -m ntl.cv --data data/proxy/comp --out artifacts/proxy_comp --compare-random --topic-folds
proxy-experiments: proxy ## about 45 minutes on 2 CPUs
	$(PY) -m ntl.proxy_experiments honesty models genre curve assign shift balance selection alarm
