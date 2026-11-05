"""Transcribe every clip under every model × condition, resumably."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly

from asr_nl.backends import Backend
from asr_nl.manifest import Clip
from asr_nl.noise import SAMPLE_RATE, apply_condition


def load_audio(path: str, max_seconds: float = 30.0) -> np.ndarray:
    """Mono float audio at 16 kHz (mp3 needs libsndfile >= 1.1)."""
    import soundfile as sf

    audio, rate = sf.read(path, dtype="float32", always_2d=True)
    audio = audio.mean(axis=1)
    if rate != SAMPLE_RATE:
        audio = resample_poly(audio, SAMPLE_RATE, rate).astype(np.float32)
    return audio[: int(max_seconds * SAMPLE_RATE)]


def prediction_path(out_dir: Path, model: str, condition: str) -> Path:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", model)
    return out_dir / f"pred__{slug}__{condition}.jsonl"


def _batches(items: list, size: int) -> Iterator[list]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def transcribe_condition(
    backend: Backend,
    clips: list[Clip],
    condition: str,
    out_dir: Path,
    *,
    loader: Callable[[str], np.ndarray] = load_audio,
    batch_size: int = 8,
    pool_size: int = 32,
) -> Path:
    """Results are appended clip by clip, so a Colab disconnect loses at most one batch."""
    path = prediction_path(out_dir, backend.name, condition)
    path.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if path.exists():
        with path.open(encoding="utf-8") as handle:
            done = {json.loads(line)["id"] for line in handle if line.strip()}
    todo = [clip for clip in clips if clip.id not in done]
    pool = [loader(c.path) for c in clips[:pool_size]] if "babble" in condition else []
    with path.open("a", encoding="utf-8") as handle:
        for chunk in _batches(todo, batch_size):
            audio = [
                apply_condition(condition, loader(c.path), c.seed, pool).astype(np.float32)
                for c in chunk
            ]
            for clip, wave, result in zip(chunk, audio, backend.transcribe(audio)):
                handle.write(json.dumps({
                    "id": clip.id,
                    "model": backend.name,
                    "condition": condition,
                    "hypothesis": result.text,
                    "avg_logprob": result.avg_logprob,
                    "seconds": result.seconds,
                    "audio_seconds": len(wave) / SAMPLE_RATE,
                }, ensure_ascii=False) + "\n")
            handle.flush()
    return path


def read_predictions(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]
