import json

import pytest

pytest.importorskip("starlette")
pytest.importorskip("multipart")
from starlette.testclient import TestClient  # noqa: E402

from beacon.auth import AuditLog, Sessions, Throttle, User, UserStore, add_user  # noqa: E402
from beacon.backends.local import LocalBackend  # noqa: E402
from beacon.embeddings import HashingEmbedder  # noqa: E402
from beacon.models import Chunk, Hit  # noqa: E402
from beacon.rag import ExtractiveGenerator  # noqa: E402
from beacon.retrieval import Retriever  # noqa: E402
from beacon.web import create_app, safe_url, snippet  # noqa: E402


@pytest.fixture
def world(tmp_path):
    embedder = HashingEmbedder()
    backend = LocalBackend()
    chunks = [
        Chunk("hr#0", "hr", 0, "", "salarisschaal directie geheim", title="Salaris", acl=["hr"]),
        Chunk("pub#0", "pub", 0, "", "begroting van de gemeente", title="Begroting",
              acl=["public"], url="javascript:alert(1)"),
        Chunk("x#0", "x", 0, "", "<script>alert(1)</script> begroting", title="<b>Kwaad</b>",
              acl=["public"]),
    ]  # fmt: skip
    backend.add(chunks, embedder.embed_passages([c.text for c in chunks]))
    users = tmp_path / "users.yaml"
    tokens = {
        "hanna": add_user(users, "hanna", ["hr", "public"]),
        "piet": add_user(users, "piet", ["public"]),
    }
    audit = tmp_path / "audit.jsonl"
    app = create_app(
        Retriever(backend, embedder), ExtractiveGenerator(), UserStore(users), AuditLog(audit)
    )
    return app, tokens, audit


def login(client, token):
    return client.post("/login", data={"token": token}, follow_redirects=False)


def test_needs_login(world):
    app, _, _ = world
    with TestClient(app) as client:
        assert client.get("/?q=begroting", follow_redirects=False).status_code == 303
        assert client.get("/document?id=pub", follow_redirects=False).status_code == 303


def test_wrong_token_is_refused_then_throttled(world):
    app, _, _ = world
    with TestClient(app) as client:
        for _ in range(10):
            assert "Onbekende" in login(client, "fout").text
        assert login(client, "fout").status_code == 429


def test_cookie_flags(world):
    app, tokens, _ = world
    with TestClient(app) as client:
        cookie = login(client, tokens["piet"]).headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie


def test_groups_decide_what_a_user_sees(world):
    app, tokens, _ = world
    with TestClient(app) as client:
        login(client, tokens["piet"])
        assert "Salaris" not in client.get("/?q=salarisschaal+directie").text
        assert client.get("/document?id=hr").status_code == 404
        assert client.get("/document?id=bestaat-niet").status_code == 404
        assert client.get("/document?id=pub").status_code == 200
        client.cookies.clear()
        login(client, tokens["hanna"])
        assert "Salaris" in client.get("/?q=salarisschaal+directie").text


def test_answers_respect_groups(world):
    app, tokens, _ = world
    with TestClient(app) as client:
        login(client, tokens["piet"])
        page = client.get("/?q=salarisschaal+directie&do=ask")
        assert "geheim" not in page.text


def test_document_text_is_escaped(world):
    app, tokens, _ = world
    with TestClient(app) as client:
        login(client, tokens["piet"])
        page = client.get("/?q=begroting")
        assert "<script>alert" not in page.text and "<b>Kwaad" not in page.text
        assert "&lt;script&gt;" in page.text
        assert "javascript:" not in page.text


def test_query_is_escaped(world):
    app, tokens, _ = world
    with TestClient(app) as client:
        login(client, tokens["piet"])
        page = client.get("/", params={"q": '"><script>x</script>'})
        assert '"><script>x' not in page.text


def test_security_headers(world):
    app, _, _ = world
    with TestClient(app) as client:
        headers = client.get("/login").headers
    assert "default-src 'none'" in headers["content-security-policy"]
    assert headers["x-content-type-options"] == "nosniff"


def test_highlight_keeps_only_engine_tags():
    hit = Hit(Chunk("a", "a", 0, "", ""), 1.0, "<em>raak</em> <img src=x onerror=y>")
    assert snippet(hit) == "<mark>raak</mark> &lt;img src=x onerror=y&gt;"


def test_snippet_drops_the_repeated_title():
    hit = Hit(Chunk("a", "a", 0, "", "Titel. Eerste zin.", title="Titel"), 1.0)
    assert snippet(hit) == "Eerste zin."


@pytest.mark.parametrize(
    ("url", "kept"),
    [("https://a.nl/x", True), ("javascript:alert(1)", False), ("data:text/html,x", False),
     ("", False)],
)  # fmt: skip
def test_safe_url(url, kept):
    assert bool(safe_url(url)) is kept


def test_api_needs_a_token_and_scopes_results(world):
    app, tokens, _ = world
    with TestClient(app) as client:
        assert client.get("/api/search?q=x").status_code == 401
        headers = {"authorization": f"Bearer {tokens['piet']}"}
        found = client.get("/api/search?q=salarisschaal", headers=headers).json()
        assert all(row["doc_id"] != "hr" for row in found["results"])
        assert client.get("/api/search?q=x&k=a", headers=headers).status_code == 400
        assert client.get("/api/search?q=x&mode=z", headers=headers).status_code == 400


def test_audit_hashes_queries_by_default(world):
    app, tokens, audit = world
    with TestClient(app) as client:
        login(client, tokens["piet"])
        client.get("/?q=begroting")
    rows = [json.loads(line) for line in audit.read_text().splitlines()]
    assert rows[0]["action"] == "login"
    assert rows[1]["user"] == "piet" and "query_sha256" in rows[1]
    assert "begroting" not in audit.read_text().replace("Begroting", "")
    assert "x" in rows[1]["documents"] or "pub" in rows[1]["documents"]


def test_audit_can_log_plain_queries(tmp_path):
    path = tmp_path / "a.jsonl"
    AuditLog(path, plain_queries=True).write("u", "search", "vraag", [])
    assert json.loads(path.read_text())["query"] == "vraag"


def mcp_call(client, token, method, params=None):
    return client.post(
        "/mcp/",
        headers={
            "authorization": f"Bearer {token}",
            "accept": "application/json, text/event-stream",
            "mcp-protocol-version": "2025-06-18",
        },
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
    )


def test_mcp_refuses_without_a_token(world):
    app, _, _ = world
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.post("/mcp/", json={}).status_code == 401
        assert mcp_call(client, "fout", "tools/list").status_code == 401


def test_mcp_is_scoped_per_user(world):
    app, tokens, _ = world
    arguments = {"name": "search", "arguments": {"query": "salarisschaal directie"}}
    with TestClient(app, base_url="http://127.0.0.1") as client:
        piet = mcp_call(client, tokens["piet"], "tools/call", arguments)
        hanna = mcp_call(client, tokens["hanna"], "tools/call", arguments)
    assert piet.status_code == 200, piet.text
    assert '\\"hr\\"' not in piet.text and '"doc_id": "hr"' not in piet.text
    assert "Salaris" in hanna.text
    assert "Salaris" not in piet.text


def test_mcp_hides_totals_and_writes_to_the_audit_log(world):
    app, tokens, audit = world
    with TestClient(app, base_url="http://127.0.0.1") as client:
        info = mcp_call(
            client, tokens["piet"], "tools/call", {"name": "index_info", "arguments": {}}
        )
        mcp_call(client, tokens["piet"], "tools/call",
                 {"name": "search", "arguments": {"query": "begroting"}})  # fmt: skip
    assert "chunks" not in info.text
    assert any(
        json.loads(line)["action"] == "mcp_search" for line in audit.read_text().splitlines()
    )


def test_mcp_refuses_a_foreign_host(world):
    app, tokens, _ = world
    with TestClient(app, base_url="http://evil.example") as client:
        assert mcp_call(client, tokens["piet"], "tools/list").status_code in (403, 421)


def test_token_is_not_stored(tmp_path):
    path = tmp_path / "u.yaml"
    token = add_user(path, "a", ["g"])
    assert token not in path.read_text()
    assert path.stat().st_mode & 0o077 == 0
    assert UserStore(path).verify(token) == User("a", frozenset({"g"}))
    assert UserStore(path).verify(token + "x") is None


def test_user_needs_a_group(tmp_path):
    with pytest.raises(ValueError):
        add_user(tmp_path / "u.yaml", "a", [])


def test_sessions_expire():
    sessions = Sessions(seconds=-1)
    assert sessions.get(sessions.create(User("a", frozenset()))) is None


def test_throttle():
    throttle = Throttle(limit=2)
    throttle.fail("x")
    assert not throttle.blocked("x")
    throttle.fail("x")
    assert throttle.blocked("x") and not throttle.blocked("y")
