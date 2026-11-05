"""Hand-written behavioural tests (in the spirit of CheckList, Ribeiro et al. 2020).

Accuracy on held-out data can't show *which* language a model fails on. This set can.
The sentences are original to this repo. Small n per category: read them as qualitative probes.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

import numpy as np

from forge.stats import wilson_interval

CHALLENGE_PATH = Path(__file__).parent / "challenge" / "behaviour_nl.jsonl"


def load_challenge(path: Path = CHALLENGE_PATH) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def run_challenge(predict: Callable[[list[str]], np.ndarray], items: list[dict]) -> dict:
    predictions = predict([item["text"] for item in items]).argmax(axis=1)
    groups = defaultdict(list)
    for item, prediction in zip(items, predictions):
        groups[item["test"]].append((item, int(prediction)))
    table, failures = [], []
    for test, results in sorted(groups.items()):
        right = sum(item["label"] == pred for item, pred in results)
        low, high = wilson_interval(right, len(results))
        table.append({"test": test, "n": len(results), "pass_rate": right / len(results),
                      "low": low, "high": high})
        failures += [item for item, pred in results if item["label"] != pred]
    return {"by_test": table, "failures": failures}
