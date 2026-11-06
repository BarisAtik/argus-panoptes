"""Users, tokens and the audit log for the web app and MCP over HTTP.

Tokens are random and 256 bits long, so a plain SHA-256 is enough to store them: there is nothing
to brute-force, unlike a password. Each user's groups live in this file on the server. Nothing in a
request can change them.

    beacon add-user alice --groups hr,finance --users data/users.yaml
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

SESSION_SECONDS = 8 * 3600
MAX_FAILURES = 10
FAILURE_WINDOW = 300


@dataclass(frozen=True)
class User:
    name: str
    groups: frozenset[str]


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class UserStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._by_hash: dict[str, User] = {}
        self.reload()

    def reload(self) -> None:
        data = {}
        if self.path.is_file():
            data = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        self._by_hash = {
            entry["token_sha256"]: User(name, frozenset(str(g) for g in entry.get("groups", [])))
            for name, entry in data.get("users", {}).items()
        }

    def __len__(self) -> int:
        return len(self._by_hash)

    def users(self) -> list[User]:
        return sorted(self._by_hash.values(), key=lambda user: user.name)

    def verify(self, token: str) -> User | None:
        candidate = hash_token(token)
        found = None
        # Every entry gets compared, so timing says nothing about which one matched.
        for stored, user in self._by_hash.items():
            if hmac.compare_digest(stored, candidate):
                found = user
        return found


def add_user(path: str | Path, name: str, groups: list[str]) -> str:
    """Create or replace a user. Returns the token, which is shown once and never stored."""
    if not groups:
        raise ValueError("a user needs at least one group")
    path = Path(path)
    data = {}
    if path.is_file():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    token = secrets.token_urlsafe(32)
    data.setdefault("users", {})[name] = {"groups": groups, "token_sha256": hash_token(token)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(mode=0o600, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=True), encoding="utf-8")
    return token


@dataclass
class Sessions:
    """Browser sessions in memory. A restart logs everyone out, which is the safe direction."""

    seconds: int = SESSION_SECONDS
    _items: dict[str, tuple[User, float]] = field(default_factory=dict)

    def create(self, user: User) -> str:
        session = secrets.token_urlsafe(32)
        self._items[hash_token(session)] = (user, time.monotonic() + self.seconds)
        return session

    def get(self, session: str) -> User | None:
        key = hash_token(session)
        item = self._items.get(key)
        if item is None:
            return None
        if item[1] < time.monotonic():
            del self._items[key]
            return None
        return item[0]

    def drop(self, session: str) -> None:
        self._items.pop(hash_token(session), None)


@dataclass
class Throttle:
    """Slow down token guessing per client address."""

    limit: int = MAX_FAILURES
    window: float = FAILURE_WINDOW
    _failures: dict[str, list[float]] = field(default_factory=dict)

    def blocked(self, client: str) -> bool:
        now = time.monotonic()
        recent = [t for t in self._failures.get(client, []) if now - t < self.window]
        self._failures[client] = recent
        return len(recent) >= self.limit

    def fail(self, client: str) -> None:
        self._failures.setdefault(client, []).append(time.monotonic())


class AuditLog:
    """One JSON line per action. Queries are hashed unless the operator chooses otherwise.

    What people search for is itself sensitive, so plain queries are opt-in.
    """

    def __init__(self, path: str | Path | None, plain_queries: bool = False):
        self.path = Path(path) if path else None
        self.plain_queries = plain_queries
        self._lock = threading.Lock()
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, user: str, action: str, query: str = "", documents: list[str] | None = None):
        if self.path is None:
            return
        entry: dict = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "user": user,
            "action": action,
        }
        if query:
            key = "query" if self.plain_queries else "query_sha256"
            entry[key] = query if self.plain_queries else hash_token(query)
        if documents is not None:
            entry["documents"] = documents
        with self._lock, open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
