"""Pins and paths. Every result names these commits, so a run can be repeated."""

from __future__ import annotations

import os
from pathlib import Path

SIGMA_REPO = "https://github.com/SigmaHQ/sigma"
SIGMA_COMMIT = "52f81d60d5ea122e49a34b2289ea0c2a7bb0b113"

DATASETS_REPO = "https://github.com/OTRF/Security-Datasets"
DATASETS_COMMIT = "d9d40ef123d2c87d5d3df28c96bcab4f0faccc87"
DATASETS_RAW = f"https://raw.githubusercontent.com/OTRF/Security-Datasets/{DATASETS_COMMIT}/"

DATA_DIR = Path(os.environ.get("NIGHTWATCH_DATA", "data"))
SIGMA_DIR = DATA_DIR / "sigma"
DATASETS_DIR = DATA_DIR / "security-datasets"
REGRESSION_CORPUS = DATA_DIR / "regression.jsonl"
ATTACK_CORPUS = DATA_DIR / "attack.jsonl"
ATTACK_INDEX = DATA_DIR / "attack-datasets.json"

ES_URL = os.environ.get("ES_URL", "http://localhost:9200")
ES_USER = os.environ.get("ES_USER", "elastic")
ES_PASSWORD = os.environ.get("ELASTIC_PASSWORD", "")
