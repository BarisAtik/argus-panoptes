"""Serve the mock world over the real Model Context Protocol.

Two uses: run a scenario with tool calls crossing an actual MCP client/server
boundary (`--transport mcp`), and expose a poisoned mock server over stdio so that
other clients and scanners can be pointed at it locally.

Capability labels stay on the client side. MCP does not carry them, which is the
point: a client must keep its own policy about what a server's tools may do.
"""

from __future__ import annotations

import argparse
import asyncio
import queue
import threading
from typing import Any

import mcp.types as mt
from mcp.client import Client
from mcp.server import Server

from .scenario import build_world, load_scenarios, new_canary
from .world import ToolSpec, World


def build_server(world: World) -> Server:
    async def on_list_tools(ctx, params) -> mt.ListToolsResult:
        return mt.ListToolsResult(tools=[
            mt.Tool(name=t.name, description=t.description, input_schema=t.json_schema()["function"]["parameters"])
            for t in world.tools()
        ])

    async def on_call_tool(ctx, params) -> mt.CallToolResult:
        text = world.call(params.name, params.arguments or {}, getattr(world, "taint_hint", False))
        return mt.CallToolResult(content=[mt.TextContent(type="text", text=text)])

    return Server("argus-gauntlet-mock", on_list_tools=on_list_tools, on_call_tool=on_call_tool)


class McpBackend:
    """Synchronous facade over an in-process MCP client session.

    anyio requires a client to be entered and exited by the same task, so one
    long-lived task owns the client and serves requests from a queue.
    """

    def __init__(self, world: World):
        self.world = world
        self._requests: queue.Queue = queue.Queue()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=lambda: asyncio.run(self._main()), daemon=True)
        self._thread.start()
        self._ready.wait(30)

    async def _main(self) -> None:
        async with Client(build_server(self.world)) as client:
            self._client = client
            self._ready.set()
            while True:
                item = await asyncio.to_thread(self._requests.get)
                if item is None:
                    return
                make, done = item
                try:
                    done.put((await make(), None))
                except Exception as exc:  # hand the failure back to the calling thread
                    done.put((None, exc))

    def _run(self, make) -> Any:
        done: queue.Queue = queue.Queue()
        self._requests.put((make, done))
        value, exc = done.get(timeout=30)
        if exc:
            raise exc
        return value

    def tools(self) -> list[ToolSpec]:
        listed = self._run(lambda: self._client.list_tools(cache_mode="bypass"))
        local = {t.name: t for t in self.world.tools()}
        out = []
        for t in listed.tools:
            spec = local.get(t.name)
            props = (t.input_schema or {}).get("properties", {})
            out.append(ToolSpec(
                t.name, t.description or "", {k: v.get("description", "") for k, v in props.items()},
                spec.labels if spec else frozenset(), spec.destination_arg if spec else None,
            ))
        return out

    def call(self, name: str, args: dict[str, Any], tainted: bool) -> str:
        self.world.taint_hint = tainted
        res = self._run(lambda: self._client.call_tool(name, args))
        return "\n".join(c.text for c in res.content if hasattr(c, "text"))

    def close(self) -> None:
        self._requests.put(None)
        self._thread.join(5)


def main() -> None:
    from mcp.server.stdio import stdio_server

    ap = argparse.ArgumentParser(description="Serve one mock scenario over MCP stdio")
    ap.add_argument("--scenario", required=True)
    args = ap.parse_args()
    sc = next(s for s in load_scenarios() if s.id == args.scenario)
    server = build_server(build_world(sc, new_canary()))

    async def serve() -> None:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    asyncio.run(serve())


if __name__ == "__main__":
    main()
