"""Storage and low-level retrieval. Fusion lives above this, in retrieval.py."""

from __future__ import annotations

from typing import Protocol

import numpy as np

from ..config import Settings
from ..models import Chunk, Filters, Hit


class Backend(Protocol):
    def create(self, dims: int, recreate: bool = False) -> None: ...

    def add(self, chunks: list[Chunk], vectors: np.ndarray) -> None: ...

    def lexical(self, query: str, k: int, filters: Filters | None = None) -> list[Hit]: ...

    def dense(self, vector: np.ndarray, k: int, filters: Filters | None = None) -> list[Hit]: ...

    def by_refs(self, refs: list[str], k: int, filters: Filters | None = None) -> list[Hit]: ...

    def term_coverage(self, query: str) -> float: ...

    def document_chunks(self, doc_id: str) -> list[Chunk]: ...

    def stats(self) -> dict: ...


def get_backend(name: str, settings: Settings) -> Backend:
    if name == "local":
        from .local import LocalBackend

        return LocalBackend()
    if name == "elastic":
        from .elastic import ElasticBackend

        return ElasticBackend.from_settings(settings)
    raise ValueError(f"unknown backend {name!r}; expected elastic or local")
