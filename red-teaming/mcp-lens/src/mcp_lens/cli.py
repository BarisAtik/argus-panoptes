"""mcp-lens command line."""

from __future__ import annotations

import argparse
import asyncio
import json
import shlex
import sys
from pathlib import Path

from .core import diff_lock, is_flagged, load_manifest, make_lock, read_json, scan, to_sarif
from .rules import Tool


async def _fetch_live(command: str) -> list[dict]:
    import mcp

    parts = shlex.split(command)
    params = mcp.StdioServerParameters(command=parts[0], args=parts[1:])
    async with mcp.Client(params) as client:
        tools, cursor = [], None
        while True:
            page = await client.list_tools(cursor=cursor)
            tools += [{"name": t.name, "description": t.description, "inputSchema": t.input_schema} for t in page.tools]
            cursor = page.next_cursor
            if not cursor:
                return tools


def fetch_live(command: str, timeout: float = 60) -> list[dict]:
    """Start a LOCAL stdio server and list its tools. Only run servers you trust to start."""
    return asyncio.run(asyncio.wait_for(_fetch_live(command), timeout))


def _gather(a) -> list[Tool]:
    tools: list[Tool] = []
    for p in a.manifest or []:
        tools += load_manifest(read_json(p), Path(p).stem)
    for cmd in a.stdio or []:
        tools += load_manifest({"server": shlex.split(cmd)[0], "tools": fetch_live(cmd)})
    if not tools:
        sys.exit("nothing to scan: give a manifest file or --stdio")
    return tools


def cmd_scan(a) -> int:
    tools = _gather(a)
    findings = scan(tools)
    if a.lock and Path(a.lock).exists():
        findings = diff_lock(tools, read_json(a.lock)) + findings
    if a.format == "json":
        print(json.dumps([f.as_dict() for f in findings], indent=2))
    elif a.format == "sarif":
        print(json.dumps(to_sarif(findings, (a.manifest or ["stdio"])[0]), indent=2))
    else:
        for f in findings:
            print(f"{f.severity.upper():6} {f.rule} {f.server}/{f.tool} [{f.field}] {f.message}")
            if f.excerpt:
                print(f"       > {f.excerpt}")
        print(f"\n{len(tools)} tools, {len(findings)} findings")
    return 1 if is_flagged(findings, a.fail_on) else 0


def cmd_pin(a) -> int:
    Path(a.lock).write_text(json.dumps(make_lock(_gather(a)), indent=2, sort_keys=True) + "\n")
    print(f"pinned to {a.lock}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="mcp-lens", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn in (("scan", cmd_scan), ("pin", cmd_pin)):
        s = sub.add_parser(name)
        s.add_argument("manifest", nargs="*", help="JSON file with a tools/list result")
        s.add_argument("--stdio", action="append", help='local server command, e.g. "uvx mcp-server-time"')
        s.add_argument("--lock", default="mcp-lens.lock.json" if name == "pin" else None)
        if name == "scan":
            s.add_argument("--format", choices=["text", "json", "sarif"], default="text")
            s.add_argument("--fail-on", choices=["low", "medium", "high"], default="high")
        s.set_defaults(fn=fn)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
