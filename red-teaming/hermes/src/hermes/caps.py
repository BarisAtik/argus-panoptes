"""Attenuating delegation tokens, in the style of macaroons.

Each holder can add a caveat, which only narrows the token, and nobody can remove one without the root key:
the signature chains through every caveat, and a holder only sees the last link.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass


def _mac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


@dataclass(frozen=True)
class Cap:
    task: str
    caveats: tuple[str, ...]
    sig: str

    def attenuate(self, caveat: str) -> "Cap":
        return Cap(self.task, (*self.caveats, caveat), _mac(bytes.fromhex(self.sig), caveat).hex())

    def to_dict(self) -> dict:
        return {"task": self.task, "caveats": list(self.caveats), "sig": self.sig}

    @classmethod
    def from_dict(cls, d: dict) -> "Cap":
        return cls(d["task"], tuple(d["caveats"]), d["sig"])


def mint(root: bytes, task: str, caveats: tuple[str, ...] = ()) -> Cap:
    cap = Cap(task, (), _mac(root, task).hex())
    for c in caveats:
        cap = cap.attenuate(c)
    return cap


def verify(root: bytes, cap: Cap) -> bool:
    sig = _mac(root, cap.task)
    for c in cap.caveats:
        sig = _mac(sig, c)
    return hmac.compare_digest(sig.hex(), cap.sig)
