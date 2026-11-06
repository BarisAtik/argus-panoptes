"""Run a mesh over the real A2A protocol: the SDK's JSON-RPC server, card routes and client.

Every agent gets its own server routes and a signed card at the well-known path. Peers resolve that card over
HTTP, the client verifies the signature, and each delegation is a real `SendMessage`. Harness fields travel in message
metadata under one key, which is where a deployment would put an A2A extension.

`tcp=True` binds a real loopback socket. It only ever binds 127.0.0.1.
"""

from __future__ import annotations

import asyncio
import json
import socket
import uuid
from typing import Any

import httpx
import uvicorn
from a2a.client import ClientConfig, create_client
from a2a.helpers.proto_helpers import get_message_text, new_text_message
from a2a.server.agent_execution import AgentExecutor
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import Message, Part, Role, SendMessageRequest
from google.protobuf.struct_pb2 import Struct
from starlette.applications import Starlette
from starlette.routing import Mount

from .cards import build_card, sign, verifier
from .core import Msg, Reply
from .mesh import Mesh, Transport

KEY = "hermes"


def _pack(obj: dict[str, Any]) -> Struct:
    s = Struct()
    s.update({KEY: json.dumps(obj)})
    return s


def _unpack(meta: Any) -> dict[str, Any]:
    return json.loads(dict(meta)[KEY])


class MeshExecutor(AgentExecutor):
    def __init__(self, mesh: Mesh, name: str):
        self.mesh, self.name = mesh, name

    async def execute(self, context, event_queue) -> None:
        h = _unpack(context.message.metadata)
        msg = Msg(h["sender"], self.name, h["skill"], get_message_text(context.message), context.context_id,
                  h["meta"], h["depth"])
        reply = await self.mesh.handle(msg)
        out = new_text_message(reply.text, context_id=context.context_id)
        out.metadata.CopyFrom(_pack({"meta": reply.meta}))
        await event_queue.enqueue_event(out)

    async def cancel(self, context, event_queue) -> None:
        raise NotImplementedError


class A2AWire(Transport):
    """A `Transport` for `Mesh`. Create it, then `await start()` before running tasks and `await stop()` after."""

    def __init__(self, mesh: Mesh, tcp: bool = False):
        self.mesh, self.tcp = mesh, tcp
        self.clients: dict[str, Any] = {}
        self.base = "http://127.0.0.1"
        self.server: uvicorn.Server | None = None
        self.task: asyncio.Task | None = None
        self.http: httpx.AsyncClient | None = None
        self.sends = 0

    def _app(self, base: str) -> Starlette:
        mounts = []
        for name in self.mesh.sc.agents:
            card = sign(build_card({"agent": name, "description": f"{name} agent", "capability": "work"},
                                   url=f"{base}/{name}/"), name)
            handler = DefaultRequestHandler(MeshExecutor(self.mesh, name), InMemoryTaskStore(), card)
            routes = [*create_agent_card_routes(card), *create_jsonrpc_routes(handler, rpc_url="/")]
            mounts.append(Mount(f"/{name}", routes=routes))
        return Starlette(routes=mounts)

    async def start(self) -> None:
        if self.tcp:
            sock = socket.socket()
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
            self.base = f"http://127.0.0.1:{port}"
            config = uvicorn.Config(self._app(self.base), log_level="error", lifespan="off")
            self.server = uvicorn.Server(config)
            self.task = asyncio.create_task(self.server.serve(sockets=[sock]))
            while not self.server.started:
                await asyncio.sleep(0.01)
            self.http = httpx.AsyncClient(base_url=self.base, timeout=30, trust_env=False)
        else:
            self.base = "http://hermes.test"
            self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=self._app(self.base)),
                                          base_url=self.base, timeout=30)

    async def stop(self) -> None:
        if self.http:
            await self.http.aclose()
        if self.server:
            self.server.should_exit = True
            await self.task

    async def _client(self, name: str):
        if name not in self.clients:
            self.clients[name] = await create_client(
                f"{self.base}/{name}/", ClientConfig(streaming=False, httpx_client=self.http),
                signature_verifier=verifier())
        return self.clients[name]

    async def deliver(self, msg: Msg) -> Reply:
        self.sends += 1
        client = await self._client(msg.receiver)
        wire = Message(message_id=uuid.uuid4().hex, context_id=msg.context, role=Role.ROLE_USER,
                       parts=[Part(text=msg.text)])
        wire.metadata.CopyFrom(_pack({"sender": msg.sender, "skill": msg.skill, "meta": msg.meta, "depth": msg.depth}))
        async for event in client.send_message(SendMessageRequest(message=wire)):
            if event.HasField("message"):
                return Reply(get_message_text(event.message), _unpack(event.message.metadata)["meta"])
        raise RuntimeError("no reply on the wire")


async def run_on_wire(sc, stack: str, seed: int = 0, tcp: bool = False):
    """Run one scenario over A2A. Returns the Mesh, so tests can compare event logs with the direct transport."""
    from .controls import build
    from .oracle import attack_success, utility
    mode = "benign" if sc.control else "compromised"
    m = Mesh(sc, build(stack), mode, seed)
    wire = A2AWire(m, tcp)
    m.transport = wire
    await wire.start()
    try:
        for i in range(len(sc.tasks)):
            await m.run_task(i)
    finally:
        await wire.stop()
    return m, (utility(m) if sc.control else attack_success(m)), wire.sends
