"""Read the CoNLL-2002 Dutch files. Articles are the unit of uncertainty, so keep their ids."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

SPLITS = {"train": "ned.train", "dev": "ned.testa", "test": "ned.testb"}


@dataclass(frozen=True)
class Sentence:
    tokens: tuple[str, ...]
    tags: tuple[str, ...]
    doc_id: str

    def with_tags(self, tags) -> Sentence:
        return replace(self, tags=tuple(tags))


def parse_conll2002(lines, split: str = "x") -> list[Sentence]:
    """Lines are `word pos iob`. `-DOCSTART-` opens an article, a blank line ends a sentence."""
    sentences: list[Sentence] = []
    doc, tokens, tags = 0, [], []

    def flush():
        if tokens:
            sentences.append(Sentence(tuple(tokens), tuple(tags), f"{split}-{doc:04d}"))
            tokens.clear()
            tags.clear()

    for raw in lines:
        line = raw.strip()
        if not line:
            flush()
            continue
        parts = line.split()
        if parts[0] == "-DOCSTART-":
            flush()
            doc += 1
            continue
        if len(parts) != 3:
            raise ValueError(f"expected `word pos iob`, got {line!r}")
        tokens.append(parts[0])
        tags.append(parts[2])
    flush()
    return sentences


def find_corpus(data_dir: str | Path | None = None) -> Path:
    """Locate the corpus folder: an explicit path, or wherever NLTK keeps it."""
    if data_dir is not None:
        path = Path(data_dir)
        if not (path / SPLITS["train"]).is_file():
            raise FileNotFoundError(f"no {SPLITS['train']} in {path}")
        return path
    import nltk

    return Path(nltk.data.find("corpora/conll2002"))


def load_split(split: str, data_dir: str | Path | None = None) -> list[Sentence]:
    path = find_corpus(data_dir) / SPLITS[split]
    # The NLTK copy is UTF-8. Read as Latin-1, `\xa0` inside `à` would split a line in two.
    with open(path, encoding="utf-8") as handle:
        return parse_conll2002(handle, split)
