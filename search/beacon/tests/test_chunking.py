import pytest
from conftest import make_document

from beacon.chunking import chunk_document
from beacon.models import Document, Section


def words(n, prefix="w"):
    return " ".join(f"{prefix}{i}" for i in range(n))


def test_short_document_is_one_chunk_with_metadata():
    document = make_document(court="Rechtbank", date="2025-01-01", subjects=["Strafrecht"])
    chunks = chunk_document(document, include_summary=False)
    assert len(chunks) == 1
    assert chunks[0].id == f"{document.id}#0"
    assert chunks[0].court == "Rechtbank"
    assert chunks[0].subjects == ["Strafrecht"]


def test_chunks_respect_the_size_limit_and_lose_no_words():
    document = make_document(text=words(1000))
    chunks = chunk_document(document, max_words=100, overlap_words=20, include_summary=False)
    assert all(len(c.text.split()) <= 100 for c in chunks)
    assert {w for c in chunks for w in c.text.split()} == set(words(1000).split())


def test_consecutive_chunks_overlap():
    document = Document(
        id="d", title="t", sections=[Section("s", [words(90, "a"), words(90, "b")])]
    )
    first, second = chunk_document(document, max_words=100, overlap_words=10, include_summary=False)
    assert first.text.split()[-10:] == second.text.split()[:10]


def test_overlap_does_not_create_a_trailing_chunk_of_only_repeated_words():
    document = make_document(text=words(100))
    assert len(chunk_document(document, 100, 20, include_summary=False)) == 1


def test_sections_are_not_mixed():
    document = Document(
        id="d", title="t", sections=[Section("Feiten", ["een"]), Section("Slot", ["twee"])]
    )
    chunks = chunk_document(document, include_summary=False)
    assert [(c.section, c.text) for c in chunks] == [("Feiten", "een"), ("Slot", "twee")]


def test_summary_can_be_excluded_for_known_item_evaluation():
    document = make_document(summary="Korte samenvatting.")
    assert "Korte samenvatting." in chunk_document(document)[0].text
    without = chunk_document(document, include_summary=False)
    assert all("samenvatting" not in c.text for c in without)


def test_overlap_must_be_smaller_than_the_chunk():
    with pytest.raises(ValueError):
        chunk_document(make_document(), max_words=10, overlap_words=10)
