"""Start `beacon mcp` as a real subprocess and call its tools over stdio.

    python evals/mcp_smoke.py
"""

from __future__ import annotations

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ARGS = ["mcp", "--backend", "local", "--corpus", "data/ak/corpus.jsonl", "--title-prefix",
        "--embedder", "onnx:data/models/multilingual-e5-small",
        "--embedding-cache", "data/embeddings", "--groups", "public"]  # fmt: skip


async def main() -> None:
    server = StdioServerParameters(command=sys.executable, args=["-m", "beacon.cli", *ARGS])
    async with stdio_client(server) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        tools = await session.list_tools()
        print("tools:", [tool.name for tool in tools.tools])
        found = await session.call_tool("search", {"query": "human oversight", "k": 2})
        result = json.loads(found.content[0].text)
        print("search:", [(r["doc_id"], r["injection_suspected"]) for r in result["results"]])
        reply = await session.call_tool("ask", {"question": "Hoe lang worden logs bewaard?"})
        print("ask:", json.loads(reply.content[0].text)["answer"][:120])


if __name__ == "__main__":
    asyncio.run(main())
