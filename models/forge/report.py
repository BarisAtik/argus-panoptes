"""Reports that can't be mistaken for results they aren't.

Every report carries a `provenance` field. "smoke" output (tiny random models, toy data) is
stamped loudly so a pipeline check can never be quoted as a finding.
"""

from __future__ import annotations

import json
import platform
import subprocess
import sys
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

SMOKE_BANNER = (
    "> **SMOKE RUN: not a result.** Tiny/random model or toy data; "
    "this only proves that the pipeline executes.\n"
)
PROVENANCES = ("real", "smoke")


def run_metadata(provenance: str, packages: Iterable[str] = (), **extra) -> dict:
    if provenance not in PROVENANCES:
        raise ValueError(f"provenance must be one of {PROVENANCES}")
    versions = {}
    for name in packages:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5
        ).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        sha = None
    return {
        "provenance": provenance,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_sha": sha,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "packages": versions,
        **extra,
    }


def _cell(value) -> str:
    if value is None:
        return "–"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value).replace("|", "\\|").replace("\n", " ")


def markdown_table(rows: Sequence[dict], columns: Sequence[str] | None = None) -> str:
    if not rows:
        return "_no rows_\n"
    columns = list(columns or rows[0].keys())
    lines = ["| " + " | ".join(columns) + " |", "|" + " --- |" * len(columns)]
    lines += ["| " + " | ".join(_cell(row.get(c)) for c in columns) + " |" for row in rows]
    return "\n".join(lines) + "\n"


def write_report(out_dir: str | Path, report: dict, markdown: str) -> tuple[Path, Path]:
    """Write report.json + report.md, adding the smoke banner where it applies."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if report.get("meta", {}).get("provenance") == "smoke":
        markdown = SMOKE_BANNER + "\n" + markdown
    json_path, md_path = out / "report.json", out / "report.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=float) + "\n",
                         encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    return json_path, md_path
