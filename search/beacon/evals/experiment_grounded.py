"""How much can a claim check catch without an LLM? Tune on half the passages, score the rest once.

Claims in `claims.jsonl` were written by a separate AI agent that never saw the checker: for each
of 80 real passages one faithful paraphrase, one close paraphrase, one subtly false claim and one
hallucinated claim. Passages are split by a hash of their id.

    python evals/experiment_grounded.py tune
    python evals/experiment_grounded.py test     # once
"""

from __future__ import annotations

import hashlib
import itertools
import json
import random
import sys
from collections import defaultdict
from dataclasses import asdict
from functools import cache
from pathlib import Path

import numpy as np

from beacon.chunking import chunk_document
from beacon.embeddings import get_embedder
from beacon.groundedness import Thresholds, check_claim
from beacon.models import read_corpus, read_jsonl
from beacon.text import sentences

HERE = Path(__file__).parent
FROZEN = HERE / "frozen-grounded.json"
RESULT = HERE.parent / "reports" / "ak-groundedness.json"
MAX_FALSE_ALARMS = 0.15


def split_of(passage: str) -> str:
    return "dev" if hashlib.sha256(passage.encode()).digest()[0] % 2 == 0 else "test"


def load():
    chunks = {
        c.id: c for d in read_corpus("data/ak/corpus.jsonl") for c in chunk_document(d)
    }
    rows = list(read_jsonl(HERE / "claims.jsonl"))
    return rows, {row["passage"]: chunks[row["passage"]].text for row in rows}


def add_mechanical(rows, passages):
    """Two failures that need no writer: a wrong source, and a quote of a changed number."""
    extra = []
    ids = sorted(passages)
    rng = random.Random(7)
    for row in rows:
        if row["type"] == "faithful_close":
            other = rng.choice([i for i in ids if i != row["passage"]])
            extra.append({**row, "type": "wrong_source", "supported": False, "passage": other,
                          "split_key": row["passage"]})  # fmt: skip
    for passage, text in passages.items():
        for sentence in sentences(text):
            digits = [w for w in sentence.split() if w.isdigit()]
            if digits:
                changed = sentence.replace(digits[0], str(int(digits[0]) + 3), 1)
                extra.append({"passage": passage, "type": "changed_number", "supported": False,
                              "trick": "", "claim": changed})  # fmt: skip
                break
    return extra


def make_embed():
    embedder = get_embedder("onnx:data/models/multilingual-e5-small", "data/cache")

    @cache
    def one(text: str) -> tuple:
        return tuple(embedder.embed_passages([text])[0])

    return lambda texts: np.array([one(text) for text in texts], dtype=np.float32)


def run(rows, passages, thresholds, embed):
    outcome = defaultdict(list)
    for row in rows:
        check = check_claim(row["claim"], [passages[row["passage"]]], thresholds, embed)
        outcome[row["type"]].append(not check.supported)
    return outcome


def rates(outcome) -> dict:
    return {kind: round(float(np.mean(flags)), 3) for kind, flags in sorted(outcome.items())}


def false_alarm(outcome) -> float:
    return float(np.mean(outcome["faithful"] + outcome["faithful_close"]))


def caught(outcome) -> float:
    return float(np.mean(outcome["subtle_false"] + outcome["hallucinated"]))


def main(stage: str) -> None:
    rows, passages = load()
    rows += add_mechanical(rows, passages)
    embed = make_embed()
    chosen = [r for r in rows if split_of(r.get("split_key", r["passage"])) == stage_split(stage)]
    if stage == "tune":
        grid = itertools.product(
            (0.4, 0.5, 0.6, 0.7, 0.8), (0.0, 0.84, 0.86, 0.88, 0.90), (True, False), (True, False)
        )
        best, best_score = None, -1.0
        for terms, similarity, modality, negation in grid:
            thresholds = Thresholds(terms, similarity, modality, negation)
            outcome = run(chosen, passages, thresholds, embed)
            if false_alarm(outcome) <= MAX_FALSE_ALARMS and caught(outcome) > best_score:
                best, best_score = thresholds, caught(outcome)
        print(best, best_score)
        frozen = asdict(best) | {"dev": rates(run(chosen, passages, best, embed))}
        FROZEN.write_text(json.dumps(frozen, indent=2) + "\n", encoding="utf-8")
        print(frozen)
        return
    if RESULT.exists():
        sys.exit(f"{RESULT} exists: the test half was already scored.")
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    thresholds = Thresholds(**{k: v for k, v in frozen.items() if k != "dev"})
    outcome = run(chosen, passages, thresholds, embed)
    tricks = defaultdict(list)
    for row in chosen:
        if row["type"] == "subtle_false":
            check = check_claim(row["claim"], [passages[row["passage"]]], thresholds, embed)
            tricks[row["trick"]].append(not check.supported)
    summary = {
        "thresholds": asdict(thresholds),
        "counts": {kind: len(flags) for kind, flags in outcome.items()},
        "flag_rate": rates(outcome),
        "false_alarm": round(false_alarm(outcome), 3),
        "caught_written": round(caught(outcome), 3),
        "subtle_by_trick": {k: [int(sum(v)), len(v)] for k, v in sorted(tricks.items())},
    }
    RESULT.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def stage_split(stage: str) -> str:
    return "dev" if stage == "tune" else "test"


if __name__ == "__main__":
    main(sys.argv[1])
