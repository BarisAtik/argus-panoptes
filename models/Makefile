.PHONY: check test lint simulate simulate-small
check: lint test
test:
	python -m pytest -q
lint:
	ruff check .
simulate:
	python -m forge.simulate --sims 800 --out docs/ci_coverage_simulation.md
simulate-small:
	python -m forge.simulate --small-groups --sims 2000
