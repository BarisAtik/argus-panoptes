"""Agent Cards built and signed with the real A2A SDK.

A signature proves who wrote a card. It says nothing about whether the card is honest, which is why
`card_sig` is measured separately from `card_pin`.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from typing import Any

import jwt
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from a2a.utils.signing import SignatureVerificationError, create_agent_card_signer, create_signature_verifier
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


@lru_cache(maxsize=None)
def _key(name: str) -> tuple[str, Any]:
    priv = ec.generate_private_key(ec.SECP256R1())
    pem = priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()
    return pem, priv.public_key()


def build_card(c: dict[str, Any], url: str = "http://127.0.0.1:9/") -> AgentCard:
    return AgentCard(
        name=c["agent"], description=c.get("description", ""), version=str(c.get("version", "1.0.0")),
        supported_interfaces=[AgentInterface(protocol_binding="JSONRPC", protocol_version="1.0", url=c.get("url", url))],
        capabilities=AgentCapabilities(streaming=False, push_notifications=bool(c.get("push"))),
        default_input_modes=["text/plain"], default_output_modes=["text/plain"],
        skills=[AgentSkill(id=c.get("capability", "work"), name=c.get("capability", "work"),
                           description=c.get("description", ""), tags=[c.get("capability", "work")])],
    )


def sign(card: AgentCard, key: str) -> AgentCard:
    pem, _ = _key(key)
    return create_agent_card_signer(pem, {"alg": "ES256", "kid": key, "typ": "JOSE"})(card)


def verifier(trusted: dict[str, Any] | None = None):
    def provider(kid, jku):
        if trusted is None:  # trust on first fetch: any key the publisher points at
            return _key(kid)[1]
        return trusted[kid]
    return create_signature_verifier(provider, ["ES256"])


def signature_ok(c: dict[str, Any]) -> bool:
    """`signature: valid` (default), `none`, or `tampered`: signed, then edited in transit."""
    state = c.get("signature", "valid")
    if state == "none":
        return False
    card = sign(build_card(c), c.get("key", c["agent"]))
    if state == "tampered":
        card.description += " (edited)"
    try:
        verifier()(card)
        return True
    except (SignatureVerificationError, jwt.PyJWTError):
        return False


def fingerprint(c: dict[str, Any]) -> str:
    keep = {k: c.get(k) for k in ("agent", "description", "capability", "key", "url")}
    return hashlib.sha256(json.dumps(keep, sort_keys=True).encode()).hexdigest()
