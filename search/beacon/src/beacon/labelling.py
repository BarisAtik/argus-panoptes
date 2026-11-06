"""Judge pooled results by hand, and save the judgements as a query file.

    beacon pool --corpus data/ak/corpus.jsonl --queries evals/hand-queries.jsonl --out pool.jsonl
    beacon label --pool pool.jsonl --out evals/hand-labels.jsonl

Progress is saved after every query, so a session can stop at any time and resume.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path

from .models import Document, read_jsonl, write_jsonl

GRADES = {"0": 0, "1": 1, "2": 2}
PROMPT = "grade 0/1/2, s to skip, q to quit: "


def load_labels(path: str | Path) -> dict[str, dict]:
    path = Path(path)
    return {row["id"]: row for row in read_jsonl(path)} if path.is_file() else {}


def label_pool(
    pool_rows: list[dict],
    documents: Mapping[str, Document],
    out: str | Path,
    ask: Callable[[str], str] = input,
    show: Callable[[str], None] = print,
) -> int:
    """Ask for a grade per pooled document. Returns the number of new judgements."""
    labels = load_labels(out)
    added = 0
    for row in pool_rows:
        entry = labels.setdefault(
            row["id"],
            {"id": row["id"], "query": row["query"], "kind": row.get("kind", ""), "relevant": {},
             "judged": []},
        )  # fmt: skip
        for doc_id in row["pool"]:
            if doc_id in entry["judged"]:
                continue
            document = documents.get(doc_id)
            show(f"\nQuery: {row['query']}")
            show(f"Document: {doc_id}\n{document.title if document else '?'}")
            if document:
                show((document.summary or document.text)[:400])
            answer = ""
            while answer not in GRADES and answer not in ("s", "q"):
                answer = ask(PROMPT).strip().lower()
            if answer == "q":
                write_jsonl(out, labels.values())
                return added
            if answer == "s":
                continue
            entry["judged"].append(doc_id)
            if GRADES[answer]:
                entry["relevant"][doc_id] = GRADES[answer]
            added += 1
        write_jsonl(out, labels.values())
    return added


def save_pool(path: str | Path, rows: list[dict]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
