"""An OpenAI-style chat endpoint for one trained Talos model, on loopback only.

It lets the code paths written for real local models run against a real learned model. Talos only knows its own tiny
language, so results through this server describe the toy.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import world as W
from .train import load, predict


MAX_USER, MAX_DATA = 30, 110


def to_example(messages: list[dict]) -> W.Example:
    user = [str(m.get("content") or "") for m in messages if m.get("role") == "user"]
    data = [str(m.get("content") or "") for m in messages if m.get("role") == "tool"]
    # The model has a fixed window. Long input is cut, keeping the end of each part, so a long page cannot crash it.
    task = (user[-1] if user else "").split()[-MAX_USER:]
    return W.Example("serve", " ".join(task), " ".join(" ".join(data).split()[-MAX_DATA:]))


def to_message(text: str) -> tuple[dict, str]:
    a = W.parse_action(text)
    if a is None:
        return {"role": "assistant", "content": text}, "stop"
    if a["tool"] == "reply":
        return {"role": "assistant", "content": a["value"]}, "stop"
    args = {"send_email": {"to": a["dest"], "body": a["value"]}, "pay": {"to": a["dest"], "amount": a["value"]},
            "read_doc": {"id": a["value"]}}[a["tool"]]
    call = {"id": uuid.uuid4().hex[:8], "type": "function", "function": {"name": a["tool"], "arguments": json.dumps(args)}}
    return {"role": "assistant", "content": text, "tool_calls": [call]}, "tool_calls"


def make_handler(model, prov: str):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code: int, body: dict):
            blob = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(blob)))
            self.end_headers()
            self.wfile.write(blob)

        def do_POST(self):
            if not self.path.endswith("/chat/completions"):
                return self._send(404, {"error": {"message": "not found"}})
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            text = predict(model, [to_example(req.get("messages", []))], prov)[0]
            msg, finish = to_message(text)
            self._send(200, {"id": "talos", "object": "chat.completion", "created": 0, "model": req.get("model", "talos"),
                             "choices": [{"index": 0, "message": msg, "finish_reason": finish}]})

    return Handler


def make_server(path: str, host: str = "127.0.0.1", port: int = 8099) -> ThreadingHTTPServer:
    if not ipaddress.ip_address(host).is_loopback:
        raise ValueError("talos serves on loopback only")
    model, cfg = load(path)
    return ThreadingHTTPServer((host, port), make_handler(model, cfg.prov))


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("model")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8099)
    a = p.parse_args(argv)
    make_server(a.model, a.host, a.port).serve_forever()


if __name__ == "__main__":
    main()
