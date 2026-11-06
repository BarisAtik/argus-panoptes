"""A small web app and HTTP API over the same retriever, with per-user access.

    beacon add-user alice --groups hr --users data/users.yaml
    beacon serve --users data/users.yaml --audit data/audit.jsonl

No JavaScript, so the browser has little to run and the content policy can be strict. All text
comes from documents and is escaped. It binds to 127.0.0.1 unless told otherwise, and it has no TLS
of its own: put a reverse proxy with TLS in front of it before anyone else connects.

Each user gets a retriever bound to their groups when the request arrives, so the checks in
retrieval.py apply on every path: search, documents, answers and MCP.
"""

from __future__ import annotations

import contextlib
import html
from dataclasses import replace
from importlib.resources import files
from urllib.parse import quote, urlsplit

from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Receive, Scope, Send

from .auth import AuditLog, Sessions, Throttle, User, UserStore
from .groundedness import best_sentence
from .injection import guard
from .mcp_server import build_server
from .models import Hit
from .rag import Answer, Generator, answer
from .retrieval import MODES, Retriever

COOKIE = "beacon_session"
MAX_QUERY = 500
MAX_K = 20
HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'self'; img-src 'self'; form-action 'self'; "
        "base-uri 'none'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


def esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def snippet(hit: Hit, query: str = "") -> str:
    """Escape everything, then restore only the engine's own highlight tags."""
    text = hit.highlight
    if not text:
        body = hit.chunk.text.removeprefix(f"{hit.chunk.title}. ")
        closest = best_sentence(query, body)[0] if query else ""
        text = (closest or body)[:320]
    return esc(text).replace("&lt;em&gt;", "<mark>").replace("&lt;/em&gt;", "</mark>")


def safe_url(url: str) -> str:
    """Only web links. A document could carry `javascript:` in its metadata."""
    try:
        return url if urlsplit(url).scheme in ("http", "https") else ""
    except ValueError:
        return ""


def page(title: str, body: str, user: User | None = None) -> str:
    header = ""
    if user:
        header = (
            f'<span class="who">{esc(user.name)}</span>'
            '<form method="post" action="/logout"><button class="link">Uitloggen</button></form>'
        )
    return f"""<!doctype html>
<html lang="nl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · Beacon</title><link rel="stylesheet" href="/style.css"></head>
<body><header><a class="brand" href="/">Beacon</a><div class="user">{header}</div></header>
<main>{body}</main>
<footer>Antwoorden komen uit uw eigen documenten en kunnen fouten bevatten. Controleer de bron.
</footer></body></html>"""


def search_form(query: str = "", mode: str = "smart") -> str:
    options = "".join(
        f'<option value="{m}"{" selected" if m == mode else ""}>{m}</option>' for m in MODES
    )
    return f"""<form class="search" action="/" method="get">
<input type="search" name="q" value="{esc(query)}" maxlength="{MAX_QUERY}" autofocus
 aria-label="Zoekvraag" placeholder="Zoek in uw documenten">
<select name="mode" aria-label="Zoekmethode">{options}</select>
<button name="do" value="search">Zoeken</button>
<button name="do" value="ask" class="secondary">Vraag stellen</button></form>"""


def result_item(hit: Hit, query: str = "", number: int | None = None) -> str:
    chunk = hit.chunk
    meta = " · ".join(esc(part) for part in (chunk.doc_type, chunk.court, chunk.date) if part)
    label = f'<span class="n">[{number}]</span> ' if number else ""
    link = f"/document?id={quote(chunk.doc_id, safe='')}"
    external = safe_url(chunk.url)
    source = f' · <a href="{esc(external)}" rel="noreferrer">bron</a>' if external else ""
    return (
        f'<li><h2>{label}<a href="{esc(link)}">{esc(chunk.title or chunk.doc_id)}</a></h2>'
        f'<p class="meta">{meta}{source}</p><p>{snippet(hit, query)}</p></li>'
    )


def answer_block(result: Answer) -> str:
    flags = ""
    if result.flagged_claims:
        items = "".join(
            f"<li>{esc(claim.claim)} <small>{esc('; '.join(claim.reasons))}</small></li>"
            for claim in result.flagged_claims
        )
        flags = f'<div class="flags"><h3>Controleer deze beweringen</h3><ul>{items}</ul></div>'
    state = f"Gegenereerd: {esc(result.generator)}"
    if result.abstained:
        state = "Geen antwoord gevonden"
    return (
        f'<section class="answer"><p class="meta">{state}</p>'
        f"<p>{esc(result.text)}</p>{flags}</section>"
    )


class McpDispatch:
    """Send an MCP request to the app of the user behind its bearer token."""

    def __init__(self, store: UserStore, throttle: Throttle, apps: dict[str, ASGIApp]):
        self.store = store
        self.throttle = throttle
        self.apps = apps

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope)
        client = request.client.host if request.client else "unknown"
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        user = None
        if not self.throttle.blocked(client) and scheme.lower() == "bearer":
            user = self.store.verify(token.strip())
        if user is None or user.name not in self.apps:
            self.throttle.fail(client)
            response = JSONResponse({"error": "unauthorised"}, 401, HEADERS)
            await response(scope, receive, send)
            return
        await self.apps[user.name](scope, receive, send)


def create_app(
    retriever: Retriever,
    generator: Generator,
    store: UserStore,
    audit: AuditLog | None = None,
    mcp: bool = True,
    allowed_hosts: list[str] | None = None,
) -> Starlette:
    audit = audit or AuditLog(None)
    sessions = Sessions()
    throttle = Throttle()
    base = replace(retriever, groups=frozenset())  # nothing, until a user is known

    def scoped(user: User) -> Retriever:
        return replace(base, groups=user.groups)

    def note_for(user: User):
        return lambda action, query, documents: audit.write(
            user.name, f"mcp_{action}", query, documents
        )

    def current(request: Request) -> User | None:
        session = request.cookies.get(COOKIE)
        return sessions.get(session) if session else None

    def bearer(request: Request) -> User | None:
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        client = request.client.host if request.client else "unknown"
        if scheme.lower() != "bearer" or throttle.blocked(client):
            return None
        user = store.verify(token.strip())
        if user is None:
            throttle.fail(client)
        return user

    def respond(body: str, status: int = 200) -> HTMLResponse:
        return HTMLResponse(body, status, HEADERS)

    async def home(request: Request) -> Response:
        user = current(request)
        if user is None:
            return RedirectResponse("/login", 303, HEADERS)
        query = request.query_params.get("q", "").strip()[:MAX_QUERY]
        mode = request.query_params.get("mode", "smart")
        mode = mode if mode in MODES else "smart"
        body = search_form(query, mode)
        if query:
            people = scoped(user)
            if request.query_params.get("do") == "ask":
                result = answer(query, people, generator, mode=mode, guard=guard)
                documents = [hit.chunk.doc_id for hit in result.contexts]
                audit.write(user.name, "ask", query, documents)
                body += answer_block(result)
                items = "".join(
                    result_item(hit, query, n) for n, hit in enumerate(result.contexts, start=1)
                )
            else:
                hits = people.search(query, mode, 10)
                audit.write(user.name, "search", query, [hit.chunk.doc_id for hit in hits])
                items = "".join(result_item(hit, query) for hit in hits)
            body += f'<ol class="results">{items}</ol>' if items else (
                '<p class="empty">Niets gevonden in de documenten die u mag lezen.</p>'
            )
        return respond(page(query or "Zoeken", body, user))

    async def document(request: Request) -> Response:
        user = current(request)
        if user is None:
            return RedirectResponse("/login", 303, HEADERS)
        doc_id = request.query_params.get("id", "")
        chunks = scoped(user).document(doc_id)
        if not chunks:
            # The same answer for missing and forbidden.
            return respond(page("Niet gevonden", '<p class="empty">Niet gevonden.</p>', user), 404)
        audit.write(user.name, "open", documents=[doc_id])
        paragraphs = "".join(f"<p>{esc(chunk.text)}</p>" for chunk in chunks)
        body = f'<article><h1>{esc(chunks[0].title)}</h1>{paragraphs}</article>'
        return respond(page(chunks[0].title or doc_id, body, user))

    async def login(request: Request) -> Response:
        client = request.client.host if request.client else "unknown"
        error = ""
        if request.method == "POST":
            if throttle.blocked(client):
                return respond(page("Inloggen", '<p class="error">Te veel pogingen.</p>'), 429)
            form = await request.form()
            user = store.verify(str(form.get("token", "")).strip())
            if user:
                audit.write(user.name, "login")
                response = RedirectResponse("/", 303, HEADERS)
                response.set_cookie(
                    COOKIE, sessions.create(user), httponly=True, samesite="strict",
                    secure=request.url.scheme == "https", max_age=sessions.seconds,
                )  # fmt: skip
                return response
            throttle.fail(client)
            error = '<p class="error">Onbekende toegangscode.</p>'
        body = f"""<form class="login" method="post" action="/login"><h1>Inloggen</h1>{error}
<label for="token">Toegangscode</label>
<input id="token" name="token" type="password" autocomplete="off" required autofocus>
<button>Inloggen</button></form>"""
        return respond(page("Inloggen", body))

    async def logout(request: Request) -> Response:
        session = request.cookies.get(COOKIE)
        if session:
            sessions.drop(session)
        response = RedirectResponse("/login", 303, HEADERS)
        response.delete_cookie(COOKIE)
        return response

    async def style(_: Request) -> Response:
        css = files("beacon.static").joinpath("style.css").read_text(encoding="utf-8")
        headers = {**HEADERS, "Cache-Control": "max-age=3600"}
        return Response(css, media_type="text/css", headers=headers)

    async def api_search(request: Request) -> Response:
        user = bearer(request)
        if user is None:
            return JSONResponse({"error": "unauthorised"}, 401, HEADERS)
        query = request.query_params.get("q", "").strip()[:MAX_QUERY]
        mode = request.query_params.get("mode", "smart")
        if mode not in MODES:
            return JSONResponse({"error": f"mode must be one of {MODES}"}, 400, HEADERS)
        try:
            k = max(1, min(int(request.query_params.get("k", "10")), MAX_K))
        except ValueError:
            return JSONResponse({"error": "k must be a number"}, 400, HEADERS)
        hits = scoped(user).search(query, mode, k)
        audit.write(user.name, "api_search", query, [hit.chunk.doc_id for hit in hits])
        results = [
            {
                "doc_id": hit.chunk.doc_id, "title": hit.chunk.title, "score": round(hit.score, 4),
                "untrusted_text": hit.highlight or hit.chunk.text[:600],
            }
            for hit in hits
        ]  # fmt: skip
        return JSONResponse({"query": query, "mode": mode, "results": results}, headers=HEADERS)

    async def health(_: Request) -> Response:
        return JSONResponse({"status": "ok"}, headers=HEADERS)

    routes = [
        Route("/", home),
        Route("/document", document),
        Route("/login", login, methods=["GET", "POST"]),
        Route("/logout", logout, methods=["POST"]),
        Route("/style.css", style),
        Route("/api/search", api_search),
        Route("/healthz", health),
    ]

    managers = []
    if mcp:
        security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=allowed_hosts or ["127.0.0.1", "127.0.0.1:*", "localhost", "localhost:*"],
            allowed_origins=[],
        )
        apps: dict[str, ASGIApp] = {}
        for user in store.users():
            server = build_server(scoped(user), generator, note_for(user))
            apps[user.name] = server.streamable_http_app(
                streamable_http_path="/",
                stateless_http=True,
                json_response=True,
                transport_security=security,
            )
            managers.append(server.session_manager)
        routes.append(Mount("/mcp", app=McpDispatch(store, throttle, apps)))

    @contextlib.asynccontextmanager
    async def lifespan(_: Starlette):
        async def nest(index: int):
            if index == len(managers):
                yield
                return
            async with managers[index].run():
                async for _ in nest(index + 1):
                    yield

        async for _ in nest(0):
            yield

    return Starlette(routes=routes, lifespan=lifespan)

