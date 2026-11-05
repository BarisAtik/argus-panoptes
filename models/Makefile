.PHONY: check test lint simulate
check: lint test
test:
	python -m pytest -q
lint:
	ruff check .
simulate:
	python -m forge.simulate --sims 800 --out docs/ci_coverage_simulation.md
