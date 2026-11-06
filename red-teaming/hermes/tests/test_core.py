import pytest

from hermes.caps import mint, verify
from hermes.core import attacker_views, b64, render, rot13, symbol, to_words, views
from hermes.mesh import derive_grants
from hermes.scenario import parse


def test_templates_chain_filters():
    assert render("{{a|b64}}", {"a": "x"}) == b64("x")
    assert render("{{a|after:zz}}", {"a": "junk zz  value"}) == "value"
    assert render("{{a|head}}/{{a|tail}}", {"a": "abcd"}) == "ab/cd"


def test_attacker_can_decode_what_dlp_cannot():
    token = "fake_tok_0123456789abcdef"
    body = token.rsplit("_", 1)[1]
    assert not any(body in v for v in views(to_words(body)))
    assert any(body in v for v in attacker_views(to_words(body)))
    assert any(token in v for v in views(b64(token)))
    assert any(token in v for v in views(rot13(token)))


def test_symbols_rebuild_the_canary():
    c = "fake_tok_" + "%016x" % 0xdeadbeef01234567
    for bits in (1, 2, 4, 8):
        raw = "".join(bin(int(symbol(c, i, bits)))[2:].zfill(bits) for i in range(64 // bits))
        assert int(raw, 2) == 0xdeadbeef01234567


def test_caps_narrow_and_cannot_be_widened():
    root = b"k" * 16
    cap = mint(root, "t", ("dests=a",))
    hop = cap.attenuate("hop=b")
    assert verify(root, cap) and verify(root, hop)
    assert not verify(b"x" * 16, hop)
    assert not verify(root, type(hop)(hop.task, hop.caveats[:-1], hop.sig))  # dropping a caveat
    assert not verify(root, type(hop)(hop.task, ("dests=a,evil", *hop.caveats[1:]), hop.sig))  # widening one
    assert not verify(root, type(hop)("other", hop.caveats, hop.sig))  # replaying into another task


def test_grants_come_from_the_task_only():
    g = derive_grants("Mail boss@corp.test and post to #eng, then pay the landlord", {"landlord": "ACCT-RENT"})
    assert g == {"boss@corp.test", "#eng", "ACCT-RENT"}


def test_validation_rejects_bad_scenarios():
    base = {"id": "x", "title": "t", "weakness": "w", "agents": {"a": {"skills": {"work": [{"reply": "ok"}]}}},
            "tasks": [{"text": "t", "entry": "a"}]}
    with pytest.raises(ValueError):
        parse(base)  # an attack needs an oracle
    with pytest.raises(ValueError):
        parse({**base, "control": True, "tasks": [{"text": "t", "entry": "nobody"}]})
    with pytest.raises(ValueError):
        parse({**base, "control": True, "agents": {"a": {"tools": ["rm_rf"], "skills": {"work": []}}}})
