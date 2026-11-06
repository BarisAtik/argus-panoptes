"""Settings, read from the environment and an optional local .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> None:
    """Load KEY=VALUE lines without overriding variables that are already set."""
    path = Path(path)
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


@dataclass(frozen=True)
class Settings:
    es_url: str = "http://localhost:9200"
    es_user: str = "elastic"
    es_password: str = ""
    index: str = "beacon-chunks"
    backend: str = "elastic"
    embedder: str = "st:intfloat/multilingual-e5-small"
    groups: str | None = None  # comma-separated; unset means no access control
    rrf_k: int = 60
    routing: str = "lang"

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            es_url=os.getenv("ES_URL", cls.es_url),
            es_user=os.getenv("ES_USER", cls.es_user),
            es_password=os.getenv("ELASTIC_PASSWORD", cls.es_password),
            index=os.getenv("BEACON_INDEX", cls.index),
            backend=os.getenv("BEACON_BACKEND", cls.backend),
            embedder=os.getenv("BEACON_EMBEDDER", cls.embedder),
            groups=os.getenv("BEACON_GROUPS"),
            rrf_k=int(os.getenv("BEACON_RRF_K", str(cls.rrf_k))),
            routing=os.getenv("BEACON_ROUTING", cls.routing),
        )
