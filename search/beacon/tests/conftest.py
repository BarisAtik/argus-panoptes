from pathlib import Path

import pytest

from beacon.backends.local import LocalBackend
from beacon.cli import demo_path, index_documents
from beacon.embeddings import HashingEmbedder
from beacon.models import Chunk, Document, Section, read_corpus
from beacon.retrieval import Retriever

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


def make_document(doc_id="ECLI:NL:XX:2025:1", text="De huurder betaalt de huur.", **fields):
    return Document(
        id=doc_id,
        title=f"{doc_id} titel",
        sections=[Section("Overwegingen", [text])],
        **fields,
    )


def make_chunk(chunk_id="a#0", doc_id="a", text="tekst", **fields):
    return Chunk(id=chunk_id, doc_id=doc_id, position=0, section="s", text=text, **fields)


@pytest.fixture
def demo_corpus():
    return read_corpus(demo_path("corpus.jsonl"))


@pytest.fixture
def demo_retriever(demo_corpus):
    backend = LocalBackend()
    embedder = HashingEmbedder(256)
    index_documents(backend, embedder, demo_corpus)
    return Retriever(backend, embedder)
