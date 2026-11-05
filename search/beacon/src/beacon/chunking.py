"""Split documents into overlapping, paragraph-aware passages.

Default sizes keep a passage under the 512-token limit of multilingual-e5-small:
Dutch legal text runs at very roughly 1.5 to 2 tokens per word, because long
compounds break into several tokens.
"""

from __future__ import annotations

from collections.abc import Iterator

from .models import Chunk, Document
from .text import sentences

DEFAULT_MAX_WORDS = 220
DEFAULT_OVERLAP_WORDS = 40


def _pieces(paragraph: str, max_words: int) -> Iterator[str]:
    """Yield a paragraph as parts of at most max_words, cutting at sentences if possible."""
    if len(paragraph.split()) <= max_words:
        yield paragraph
        return
    buffer: list[str] = []
    for sentence in sentences(paragraph):
        words = sentence.split()
        if len(words) > max_words:
            if buffer:
                yield " ".join(buffer)
                buffer = []
            for start in range(0, len(words), max_words):
                yield " ".join(words[start : start + max_words])
            continue
        if len(buffer) + len(words) > max_words:
            yield " ".join(buffer)
            buffer = []
        buffer.extend(words)
    if buffer:
        yield " ".join(buffer)


def _chunk(doc: Document, position: int, section: str, text: str) -> Chunk:
    return Chunk(
        id=f"{doc.id}#{position}",
        doc_id=doc.id,
        position=position,
        section=section,
        text=text,
        title=doc.title,
        court=doc.court,
        date=doc.date,
        doc_type=doc.doc_type,
        subjects=list(doc.subjects),
        url=doc.url,
    )


def chunk_document(
    doc: Document,
    max_words: int = DEFAULT_MAX_WORDS,
    overlap_words: int = DEFAULT_OVERLAP_WORDS,
    include_summary: bool = True,
) -> list[Chunk]:
    """Chunk one document.

    Set include_summary=False for known-item evaluation. Otherwise the summary that
    serves as the query is also in the index and every score is inflated.
    """
    if overlap_words >= max_words:
        raise ValueError("overlap_words must be smaller than max_words")

    chunks: list[Chunk] = []
    if include_summary and doc.summary.strip():
        for piece in _pieces(doc.summary.strip(), max_words):
            chunks.append(_chunk(doc, len(chunks), "Inhoudsindicatie", piece))

    for section in doc.sections:
        buffer: list[str] = []
        carried = 0  # words in buffer that repeat the previous chunk

        def flush(title: str = section.title) -> None:
            nonlocal buffer, carried
            if len(buffer) > carried:
                chunks.append(_chunk(doc, len(chunks), title, " ".join(buffer)))
                buffer = buffer[-overlap_words:] if overlap_words else []
                carried = len(buffer)

        for paragraph in section.paragraphs:
            for piece in _pieces(paragraph.strip(), max_words):
                words = piece.split()
                if not words:
                    continue
                if len(buffer) + len(words) > max_words:
                    flush()
                    if len(buffer) + len(words) > max_words:
                        buffer = []
                        carried = 0
                buffer.extend(words)
        flush()
    return chunks
