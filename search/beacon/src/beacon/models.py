"""Plain data types shared by the pipeline."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path

PUBLIC = "public"


@dataclass
class Section:
    title: str
    paragraphs: list[str]


@dataclass
class Document:
    id: str
    title: str
    court: str = ""
    date: str = ""
    doc_type: str = ""
    subjects: list[str] = field(default_factory=list)
    case_numbers: list[str] = field(default_factory=list)
    procedure: list[str] = field(default_factory=list)
    place: str = ""
    summary: str = ""
    url: str = ""
    sections: list[Section] = field(default_factory=list)
    acl: list[str] = field(default_factory=lambda: [PUBLIC])

    @property
    def text(self) -> str:
        return "\n".join(p for s in self.sections for p in s.paragraphs)

    @classmethod
    def from_dict(cls, data: dict) -> Document:
        data = dict(data)
        data["sections"] = [Section(**s) for s in data.get("sections", [])]
        return cls(**data)


@dataclass
class Chunk:
    id: str
    doc_id: str
    position: int
    section: str
    text: str
    title: str = ""
    court: str = ""
    date: str = ""
    doc_type: str = ""
    subjects: list[str] = field(default_factory=list)
    url: str = ""
    acl: list[str] = field(default_factory=list)

    def source(self) -> dict:
        return asdict(self)


@dataclass
class Filters:
    court: str | None = None
    subject: str | None = None
    doc_type: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    # None means no access control, for a trusted operator. An empty set matches nothing.
    groups: frozenset[str] | None = None

    def matches(self, chunk: Chunk) -> bool:
        if self.groups is not None and not self.groups.intersection(chunk.acl):
            return False
        if self.court and chunk.court != self.court:
            return False
        if self.subject and self.subject not in chunk.subjects:
            return False
        if self.doc_type and chunk.doc_type != self.doc_type:
            return False
        if self.date_from and (not chunk.date or chunk.date < self.date_from):
            return False
        if self.date_to and (not chunk.date or chunk.date > self.date_to):
            return False
        return True


@dataclass
class Hit:
    chunk: Chunk
    score: float
    highlight: str = ""


def read_jsonl(path: str | Path) -> Iterator[dict]:
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def write_jsonl(path: str | Path, rows: Iterable[dict]) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def read_corpus(path: str | Path) -> list[Document]:
    return [Document.from_dict(row) for row in read_jsonl(path)]
