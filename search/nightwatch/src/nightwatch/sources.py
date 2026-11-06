"""Download public rules and logs at run time, pinned to a commit. Nothing is committed here.

Sigma rules: Detection Rule License 1.1. Security-Datasets: MIT. Both are simulated lab activity,
with lab account names, so there is no real person's data in the logs.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import yaml

from . import config
from .events import flatten_evtx, read_zip_events

SPLIT_SALT = "nightwatch-v1"


def split_of(key: str) -> str:
    """One fifth is dev. Stable, and independent of order and of content."""
    digest = hashlib.sha256(f"{SPLIT_SALT}:{key}".encode()).digest()
    return "dev" if digest[0] % 5 == 0 else "test"


def _git(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, timeout=300)


def fetch_pinned(repo: str, commit: str, dest: Path, sparse: list[str] | None = None) -> None:
    if (dest / ".git").exists():
        return
    dest.mkdir(parents=True, exist_ok=True)
    _git("init", "-q", cwd=dest)
    _git("remote", "add", "origin", repo, cwd=dest)
    if sparse:
        _git("config", "core.sparseCheckout", "true", cwd=dest)
        _git("sparse-checkout", "set", *sparse, cwd=dest)
        _git("fetch", "-q", "--depth", "1", "--filter=blob:limit=100k", "origin", commit, cwd=dest)
    else:
        _git("fetch", "-q", "--depth", "1", "origin", commit, cwd=dest)
    _git("checkout", "-q", "FETCH_HEAD", cwd=dest)


def fetch_sigma(dest: Path = config.SIGMA_DIR) -> None:
    fetch_pinned(config.SIGMA_REPO, config.SIGMA_COMMIT, dest)


def regression_cases(sigma_dir: Path = config.SIGMA_DIR) -> Iterator[dict[str, Any]]:
    """Sigma's own positive samples: per rule, logs that it must fire on, and how many times."""
    for info_path in sorted((sigma_dir / "regression_data").rglob("info.yml")):
        info = yaml.safe_load(info_path.read_text(encoding="utf-8"))
        rule_id = info["rule_metadata"][0]["id"]
        tests = info.get("regression_tests_info") or []
        sample = info_path.parent / f"{rule_id}.json"
        if not tests or not sample.exists():
            continue
        yield {
            "case_id": rule_id,
            "match_count": int(tests[0].get("match_count", 1)),
            "sample": sample,
            "split": split_of(rule_id),
        }


def read_sample(path: Path) -> list[dict[str, str]]:
    """A sample is one JSON object, a list, or several objects in a row."""
    text = path.read_text(encoding="utf-8", errors="replace")
    decoder = json.JSONDecoder()
    records, position = [], 0
    while position < len(text):
        while position < len(text) and text[position].isspace():
            position += 1
        if position >= len(text):
            break
        value, position = decoder.raw_decode(text, position)
        records.extend(value if isinstance(value, list) else [value])
    return [flatten_evtx(record) for record in records]


def write_regression_corpus(out: Path = config.REGRESSION_CORPUS) -> dict[str, dict]:
    """Returns case metadata by rule id."""
    out.parent.mkdir(parents=True, exist_ok=True)
    cases: dict[str, dict] = {}
    with out.open("w", encoding="utf-8") as handle:
        for case in regression_cases():
            events = read_sample(case["sample"])
            cases[case["case_id"]] = {
                "match_count": case["match_count"],
                "events": len(events),
                "split": case["split"],
            }
            for event in events:
                event.update(case_id=case["case_id"], split=case["split"])
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    out.with_suffix(".cases.json").write_text(json.dumps(cases, indent=1), encoding="utf-8")
    return cases


def attack_metadata(root: Path = config.DATASETS_DIR) -> list[dict[str, Any]]:
    """Windows atomic datasets that have host logs. Author names are deliberately not kept."""
    records = []
    for path in sorted((root / "datasets/atomic/_metadata").glob("SDWIN-*.yaml")):
        meta = yaml.safe_load(path.read_text(encoding="utf-8"))
        links = [f["link"] for f in meta.get("files") or [] if f.get("type") == "Host"]
        if not links:
            continue
        techniques = []
        for mapping in meta.get("attack_mappings") or []:
            technique = str(mapping.get("technique") or "").strip()
            sub = mapping.get("sub-technique")
            if technique:
                techniques.append(f"{technique}.{sub}" if sub else technique)
        records.append(
            {
                "dataset_id": meta["id"],
                "title": meta.get("title", ""),
                "created": str(meta.get("creation_date", "")).replace("/", "-"),
                "techniques": sorted(set(techniques)),
                "links": links,
                "split": split_of(meta["id"]),
            }
        )
    return records


def download_attack_logs(root: Path = config.DATASETS_DIR) -> list[dict[str, Any]]:
    fetch_pinned(
        config.DATASETS_REPO, config.DATASETS_COMMIT, root, sparse=["datasets/atomic/_metadata"]
    )
    records = attack_metadata(root)
    zips = root / "zips"
    zips.mkdir(exist_ok=True)
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        for record in records:
            record["files"] = []
            for link in record["links"]:
                relative = link.split("/master/", 1)[-1]
                target = zips / relative.replace("/", "__")
                record["files"].append(target.name)
                if target.exists():
                    continue
                response = client.get(config.DATASETS_RAW + relative)
                if response.status_code == 200:
                    target.write_bytes(response.content)
    return records


def write_attack_corpus(out: Path = config.ATTACK_CORPUS) -> list[dict[str, Any]]:
    records = download_attack_logs()
    zips = config.DATASETS_DIR / "zips"
    out.parent.mkdir(parents=True, exist_ok=True)
    kept = []
    with out.open("w", encoding="utf-8") as handle:
        for record in records:
            count = 0
            for name in record.pop("files"):
                path = zips / name
                if not path.exists() or not zipfile.is_zipfile(path):
                    continue  # some links are dead or point at stubs
                for event in read_zip_events(path):
                    event.update(dataset_id=record["dataset_id"], split=record["split"])
                    handle.write(json.dumps(event, ensure_ascii=False) + "\n")
                    count += 1
            record["events"] = count
            record.pop("links")
            if count:
                kept.append(record)
    config.ATTACK_INDEX.write_text(json.dumps(kept, indent=1), encoding="utf-8")
    return kept
