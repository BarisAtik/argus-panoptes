"""One JSONL format for any speech dataset, plus an audit of what the sample really contains."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class Clip:
    id: str
    path: str
    text: str
    speaker: str
    accent: str = ""
    gender: str = ""
    age: str = ""

    @property
    def seed(self) -> int:
        """Stable per-clip seed: every model hears exactly the same noise."""
        return int.from_bytes(hashlib.sha256(self.id.encode()).digest()[:4], "big")


def write_manifest(clips: Iterable[Clip], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for clip in clips:
            handle.write(json.dumps(asdict(clip), ensure_ascii=False) + "\n")


def read_manifest(path: str | Path) -> list[Clip]:
    with Path(path).open(encoding="utf-8") as handle:
        return [Clip(**json.loads(line)) for line in handle if line.strip()]


def from_common_voice_tsv(tsv: str | Path, clips_dir: str | Path) -> list[Clip]:
    """Parse a Common Voice split file. Speaker ids are hashed again: we never need raw ones."""
    clips = []
    with Path(tsv).open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t", quoting=csv.QUOTE_NONE):
            sentence = (row.get("sentence") or "").strip()
            name = (row.get("path") or "").strip()
            if not sentence or not name:
                continue
            speaker = hashlib.sha256((row.get("client_id") or "").encode()).hexdigest()[:12]
            clips.append(Clip(
                id=Path(name).stem,
                path=str(Path(clips_dir) / name),
                text=sentence,
                speaker=speaker,
                accent=(row.get("accents") or row.get("accent") or "").strip(),
                gender=(row.get("gender") or "").strip(),
                age=(row.get("age") or "").strip(),
            ))
    return clips


def sample_clips(
    clips: list[Clip], n: int, *, per_speaker_cap: int = 5, seed: int = 0
) -> list[Clip]:
    """Round-robin over shuffled speakers, so that prolific speakers can't dominate the sample."""
    rng = np.random.default_rng(seed)
    by_speaker: dict[str, list[Clip]] = defaultdict(list)
    for clip in sorted(clips, key=lambda c: c.id):
        by_speaker[clip.speaker].append(clip)
    speakers = sorted(by_speaker)
    rng.shuffle(speakers)
    for speaker in speakers:
        rng.shuffle(by_speaker[speaker])
    chosen: list[Clip] = []
    for round_index in range(per_speaker_cap):
        for speaker in speakers:
            if len(chosen) >= n:
                return chosen
            if round_index < len(by_speaker[speaker]):
                chosen.append(by_speaker[speaker][round_index])
    return chosen


def audit(clips: list[Clip]) -> dict:
    """What is in this sample, and who is missing? Reported with every result."""
    speakers = Counter(c.speaker for c in clips)
    counts = sorted(speakers.values(), reverse=True)
    top_decile = max(1, len(counts) // 10)
    report = {
        "clips": len(clips),
        "speakers": len(speakers),
        "clips_per_speaker_median": float(np.median(counts)) if counts else 0.0,
        "top_10pct_speakers_share_of_clips": sum(counts[:top_decile]) / max(1, len(clips)),
        "duplicate_sentences": len(clips) - len({c.text for c in clips}),
    }
    for field in ("accent", "gender", "age"):
        values = Counter(getattr(c, field) or "(missing)" for c in clips)
        report[field] = dict(values.most_common())
        report[f"{field}_missing_share"] = values["(missing)"] / max(1, len(clips))
    warnings = []
    if report["top_10pct_speakers_share_of_clips"] > 0.5:
        warnings.append("A few speakers dominate; every estimate is driven by them.")
    for field in ("accent", "gender", "age"):
        if report[f"{field}_missing_share"] > 0.3:
            warnings.append(f"{field} is missing for over 30% of clips: slices are not "
                            "representative of the sample, let alone of Dutch speakers.")
    report["warnings"] = warnings
    return report
