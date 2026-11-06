"""Change the input in ways a real pipeline would, keeping the gold spans valid."""

from __future__ import annotations

import string
from collections.abc import Sequence

from .data import Sentence
from .spans import bio_spans, spans_to_bio

PUNCTUATION = set(string.punctuation) | set("«»“”‘’…–—")


def lowercase(sentences: Sequence[Sentence]) -> list[Sentence]:
    return [Sentence(tuple(t.lower() for t in s.tokens), s.tags, s.doc_id) for s in sentences]


def _is_punct(token: str) -> bool:
    return all(c in PUNCTUATION for c in token)


def transcript_style(sentences: Sequence[Sentence]) -> list[Sentence]:
    """Lowercase, no punctuation tokens: roughly what a speech recogniser hands downstream.

    Gold spans shrink around dropped tokens. A span that was punctuation only disappears, and an
    empty sentence stays empty so that sentences keep their positions.
    """
    out = []
    for s in sentences:
        keep = [i for i, t in enumerate(s.tokens) if not _is_punct(t)]
        new_index = {old: new for new, old in enumerate(keep)}
        spans = []
        for start, end, label in bio_spans(s.tags):
            inside = [new_index[i] for i in range(start, end) if i in new_index]
            if inside:
                spans.append((inside[0], inside[-1] + 1, label))
        tags = spans_to_bio(spans, len(keep))
        out.append(Sentence(tuple(s.tokens[i].lower() for i in keep), tuple(tags), s.doc_id))
    return out
