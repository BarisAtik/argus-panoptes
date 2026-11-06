"""The protocol layer. Direct and A2A runs must agree, or the factorial would not describe real A2A traffic."""

import asyncio
import json

import httpx
import pytest
from a2a.utils.signing import InvalidSignaturesError, NoSignatureError

from hermes.cards import build_card, sign, signature_ok, verifier
from hermes.controls import build
from hermes.factorial import attack_cell, control_cells
from hermes.mesh import Mesh
from hermes.runner import run
from hermes.scenario import load
from hermes.wire import A2AWire, run_on_wire

STACKS = ["none", "caps", "taint_inband", "taint_lineage", "taint_hwm", "full"]
CASES = [attack_cell("exfil", 2, "base64", "partner", "declared", "rogue_relay", "none"),
         attack_cell("action", 3, "verbatim", "attacker", "undeclared", "hijacked", "store"),
         control_cells()[0]] + [s for s in load() if s.id in (
             "session-smuggling", "push-callback-exfil", "typed-amount-tamper", "surface-ctl-lookup-pay")]


def outcome(sc, stack):
    r = run(sc, stack)
    return r.util if sc.control else r.attack


@pytest.mark.parametrize("sc", CASES, ids=lambda s: s.id)
@pytest.mark.parametrize("stack", STACKS)
def test_a2a_matches_direct(sc, stack):
    _, ok, sends = asyncio.run(run_on_wire(sc, stack))
    assert ok == outcome(sc, stack)
    assert sends > 0


def test_real_loopback_socket_and_card_discovery():
    async def go():
        sc = CASES[0]
        m = Mesh(sc, build("none"), "compromised", 0)
        wire = A2AWire(m, tcp=True)
        m.transport = wire
        await wire.start()
        try:
            assert wire.base.startswith("http://127.0.0.1:")
            async with httpx.AsyncClient(trust_env=False) as c:
                card = (await c.get(f"{wire.base}/vault/.well-known/agent-card.json")).json()
            assert card["name"] == "vault" and card["signatures"]
            await m.run_task(0)
        finally:
            await wire.stop()
        return m
    m = asyncio.run(go())
    assert any(e.kind == "ask" for e in m.events)


def test_labels_really_travel_in_message_metadata():
    from hermes import wire as w
    assert w._unpack(w._pack({"meta": {"labels": ["private"]}})) == {"meta": {"labels": ["private"]}}
    json.dumps(w._unpack(w._pack({"a": 1})))


def test_sdk_verifier_accepts_valid_and_rejects_tampered_or_missing():
    card = sign(build_card({"agent": "a", "description": "d"}), "a")
    verifier()(card)
    card.description = "changed"
    with pytest.raises(InvalidSignaturesError):
        verifier()(card)
    with pytest.raises(NoSignatureError):
        verifier()(build_card({"agent": "a"}))


def test_signed_card_from_attacker_key_passes_tofu_and_fails_a_key_allowlist():
    from hermes.cards import _key
    card = sign(build_card({"agent": "mailer"}), "attacker")
    verifier()(card)  # trust on first fetch accepts any publisher key
    with pytest.raises((KeyError, InvalidSignaturesError)):
        verifier({"mailer": _key("mailer")[1]})(card)


def test_signature_ok_states():
    assert signature_ok({"agent": "a"})
    assert not signature_ok({"agent": "a", "signature": "none"})
    assert not signature_ok({"agent": "a", "signature": "tampered"})
