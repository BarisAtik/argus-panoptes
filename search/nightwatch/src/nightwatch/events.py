"""Turn the two public log formats into one flat, all-string event shape.

Sigma rules use native Windows field names, and both sources keep them, so nothing is renamed
except the provider. All values become strings: a rule's `EventID: 1` must behave the same on
every engine, and that is simpler to reason about with one type.
"""

from __future__ import annotations

import json
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

MAX_UNCOMPRESSED = 400_000_000  # refuse a member that inflates past this
META_FIELDS = ("case_id", "dataset_id", "split")


def _text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "\n".join(_text(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def flatten_evtx(record: dict[str, Any]) -> dict[str, str]:
    """Flatten evtx-as-JSON: `{"Event": {"System": ..., "EventData": ...}}`."""
    event = record.get("Event", record)
    system = event.get("System") or {}
    provider = (system.get("Provider") or {}).get("#attributes") or {}
    flat: dict[str, str] = {}
    for section in ("EventData", "UserData"):
        data = event.get(section)
        if not isinstance(data, dict):
            continue
        if section == "UserData" and len(data) == 1:  # one wrapper element with a schema name
            only = next(iter(data.values()))
            data = only if isinstance(only, dict) else data
        for key, value in data.items():
            if key.startswith("#") or value is None:
                continue
            flat[key] = _text(value)
    for key in ("Channel", "EventID", "Computer", "Level", "Task", "Keywords"):
        value = system.get(key)
        if isinstance(value, dict):  # EventID can carry a Qualifiers attribute
            value = value.get("#text")
        if value is not None:
            flat[key] = _text(value)
    if provider.get("Name"):
        flat["Provider_Name"] = provider["Name"]
    return flat


def normalise_flat(event: dict[str, Any]) -> dict[str, str]:
    """Security-Datasets events are already flat. Only the provider name differs."""
    flat = {key: _text(value) for key, value in event.items() if value is not None}
    if "SourceName" in flat:
        flat.setdefault("Provider_Name", flat["SourceName"])
    for noisy in ("@timestamp", "@version", "tags", "port"):
        flat.pop(noisy, None)
    return flat


def read_zip_events(path: Path) -> Iterator[dict[str, str]]:
    """Read JSON-lines members in memory. Nothing is extracted to disk."""
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir() or info.file_size > MAX_UNCOMPRESSED:
                continue
            if not info.filename.lower().endswith(".json"):
                continue
            with archive.open(info) as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(event, dict):
                        yield normalise_flat(event)
