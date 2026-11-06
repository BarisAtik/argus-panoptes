.PHONY: install up up-kibana up-app down test lint demo fetch ingest eval real-data

install:
	pip install -e ".[dev,web,files]"

up:
	docker compose up -d elasticsearch

up-kibana:
	docker compose --profile kibana up -d

up-app:
	docker compose --profile app up -d --build

down:
	docker compose --profile kibana --profile app down

test:
	pytest

lint:
	ruff check src tests

# No Docker, no model download: synthetic corpus, in-process backend.
demo:
	beacon search --backend local --embedder hash --demo "inbraak in een woning"
	beacon ask --backend local --embedder hash --demo "Wanneer mag een verhuurder de huur verhogen?"

fetch:
	beacon fetch --date-from 2024-01-01 --date-to 2024-01-31 --max-docs 500

ingest:
	beacon ingest --corpus data/corpus.jsonl --recreate

eval:
	beacon eval --backend local --embedder hash --demo

# Real Dutch text and independent labels, no Docker and no torch.
real-data:
	pip install -e ".[onnx,compounds]"
	beacon fetch-ak
	beacon fetch-model
