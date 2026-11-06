#!/usr/bin/env python3
"""Check a write-up against the contest limits: at most 2,000 words, fewer than 10 figures/tables.

    python scripts/check_writeup.py WRITEUP.md

Words exclude HTML comments, code blocks, tables and image lines, on the assumption that the limit
applies to prose. Read the rules on this, and leave a margin if they count differently.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

MAX_WORDS, MAX_VISUALS = 2000, 9


def measure(text: str) -> tuple[int, int]:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    lines = text.splitlines()
    images = sum(bool(re.search(r"!\[.*?\]\(.*?\)", ln)) for ln in lines)
    tables = sum(bool(re.match(r"\s*\|?[\s:-]*-{3,}[\s:|-]*\|?\s*$", ln)) and "|" in ln
                 for ln in lines)
    prose = [ln for ln in lines
             if not ln.lstrip().startswith("|") and not re.search(r"!\[.*?\]\(.*?\)", ln)]
    return len(" ".join(prose).split()), images + tables


def main() -> int:
    words, visuals = measure(Path(sys.argv[1]).read_text())
    print(f"{words} words (max {MAX_WORDS}), {visuals} figures/tables (max {MAX_VISUALS})")
    return 0 if words <= MAX_WORDS and visuals <= MAX_VISUALS else 1


if __name__ == "__main__":
    raise SystemExit(main())
