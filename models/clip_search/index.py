"""A flat in-memory index: exact cosine search, plenty for tens of thousands of images."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from clip_search.backends import Backend


def load_image(path: str):
    from PIL import Image

    with Image.open(path) as image:
        return image.convert("RGB")


def embed_paths(
    backend: Backend,
    paths: list[str],
    *,
    transform: Callable | None = None,
    batch_size: int = 32,
    progress: bool = False,
) -> np.ndarray:
    chunks = []
    for start in range(0, len(paths), batch_size):
        images = [load_image(p) for p in paths[start : start + batch_size]]
        chunks.append(backend.encode_images([transform(i) if transform else i for i in images]))
        if progress and start % (batch_size * 20) == 0:
            print(f"{start + len(images)}/{len(paths)}", flush=True)
    return np.concatenate(chunks)


@dataclass
class ImageIndex:
    embeddings: np.ndarray
    ids: list[str]

    def search(self, query: np.ndarray, k: int = 12) -> list[tuple[str, float]]:
        scores = self.embeddings @ query
        top = np.argsort(-scores)[:k]
        return [(self.ids[i], float(scores[i])) for i in top]

    def save(self, folder: str | Path) -> None:
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        np.save(folder / "embeddings.npy", self.embeddings.astype(np.float32))
        (folder / "ids.json").write_text(json.dumps(self.ids), encoding="utf-8")

    @classmethod
    def load(cls, folder: str | Path) -> ImageIndex:
        folder = Path(folder)
        ids = json.loads((folder / "ids.json").read_text(encoding="utf-8"))
        return cls(np.load(folder / "embeddings.npy"), ids)
