import pytest

pytest.importorskip("agentdojo")

from gauntlet.agentdojo_bridge import PolicyState, destinations, to_markdown, worst_case  # noqa: E402


def test_destinations_reads_lists_and_strings():
    assert destinations("send_email", {"recipients": ["a@x.test"], "cc": None, "bcc": ["b@x.test"]}) == ["a@x.test", "b@x.test"]
    assert destinations("get_iban", {}) == []


def test_policy_decisions():
    s = PolicyState("allowlist+contacts", {"send_money"}, "pay bob", "bob@x.test iban123")
    assert s.decide("send_email", {"recipients": ["a"]}) == "tool not needed for this task"
    assert s.decide("send_money", {"recipient": "evil"}) == "destination is not a known contact"
    assert s.decide("send_money", {"recipient": "IBAN123"}) is None


def test_end_to_end_on_the_smallest_suite_and_blocked_calls_do_not_count():
    res = worst_case(["slack"], ["none", "allowlist"], workers=1)
    s = res["summary"]
    assert s["none"]["asr"]["rate"] == 1.0
    assert s["none"]["benign_utility"]["rate"] == 1.0  # ground truth solves every task
    assert s["allowlist"]["asr"]["rate"] <= 0.21  # trace-based checks must not see blocked calls
    assert "No language model" in to_markdown(res)


def test_model_mode_runs_against_a_local_stub():
    """Plumbing only: the stub never calls a tool, so nothing about security is shown here."""
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from gauntlet.agentdojo_bridge import run_model

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["content-length"]))
            body = json.dumps({"id": "x", "object": "chat.completion", "created": 0, "model": "m", "choices": [
                {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "ok"}}]}).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    res = run_model(["slack"], ["none", "allowlist"], "m", f"http://127.0.0.1:{srv.server_port}/v1", "ignore_previous", 2)
    srv.shutdown()
    assert res["summary"]["none"]["asr"]["n"] == 2
    assert res["summary"]["none"]["asr"]["k"] == 0


def test_model_mode_refuses_remote_endpoint():
    from gauntlet.agentdojo_bridge import run_model

    with pytest.raises(ValueError):
        run_model(["slack"], ["none"], "m", "https://api.example.com/v1", "ignore_previous", 1)
