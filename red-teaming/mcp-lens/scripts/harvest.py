#!/usr/bin/env python3
"""Snapshot tools/list from public MCP servers into corpus/real/ (kept out of git).

Run this yourself, in a throwaway container: starting a server runs its package code.
The snapshots are other people's text, so the repo keeps this script and the
resulting numbers but not the descriptions themselves.
"""

import json
import re
import sys
from pathlib import Path

from mcp_lens.cli import fetch_live

root = Path(__file__).resolve().parent.parent
out = root / "corpus" / "real"
out.mkdir(exist_ok=True)
for line in (root / "corpus" / "servers.txt").read_text().splitlines():
    if not line.strip() or line.startswith("#"):
        continue
    slug = re.sub(r"\W+", "-", line.replace("npx -y ", "").replace("uvx ", "").split()[0]).strip("-")
    try:
        tools = fetch_live(line, timeout=120)
        (out / f"{slug}.json").write_text(json.dumps({"server": slug, "tools": tools}, indent=1))
        print(f"ok   {slug}: {len(tools)} tools")
    except BaseException as exc:  # one broken server must not end the harvest
        print(f"skip {slug}: {type(exc).__name__}", file=sys.stderr)
