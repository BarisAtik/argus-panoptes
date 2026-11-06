.PHONY: test fetch up

test:
	pytest -q
	ruff check src tests evals

fetch:
	nightwatch fetch

up:
	docker compose up -d elasticsearch
