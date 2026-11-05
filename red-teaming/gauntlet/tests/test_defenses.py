"""Each defense must stop what it claims to stop, and each known gap stays pinned.

A test named `..._gap` documents a real limitation. If one fails after a change,
the gap closed: update the write-up rather than the test.
"""

import pytest

from gauntlet.agents import make_agent
from gauntlet.defenses import PROFILES, ablations, make_stack
from gauntlet.runner import run_trial
from gauntlet.scenario import load_scenarios

BY = {s.id: s for s in load_scenarios()}


def t(sid, defense, agent="compromised", seed=0):
    return run_trial(BY[sid], lambda: make_agent(agent), defense, seed)


@pytest.mark.parametrize("sid,defense", [
    ("ipi-email-blunt", "allowlist"),
    ("ipi-doc-polite", "egress"),
    ("ipi-web-private-in-task", "trifecta"),
    ("exfil-base64", "dlp"),
    ("exfil-allowed-sink-plain", "dlp"),
    ("exfil-chunked", "egress"),
    ("exfil-markdown-image", "output_filter"),
    ("exfil-get-query", "egress"),
    ("misuse-payee-swap", "provenance"),
    ("misuse-amount-inflate", "provenance"),
    ("priv-other-credential", "scoped_secrets"),
    ("sc-tool-description-poison", "manifest_scan"),
    ("sc-rug-pull", "tool_pin"),
    ("sc-tool-shadowing", "egress"),
    ("exec-readme-pipe", "exec_guard"),
    ("mem-two-session", "memory_guard"),
    ("res-bulk-mail", "rate_limit"),
    ("ipi-email-blunt", "injection_filter"),
])
def test_defense_stops_scenario(sid, defense):
    assert t(sid, "none").attack
    assert not t(sid, defense).attack


@pytest.mark.parametrize("sid,defense", [
    ("ipi-dutch", "injection_filter"),            # the filter only knows English phrases
    ("sc-tool-description-subtle", "manifest_scan"),  # nothing alarming to match
    ("exfil-chunked", "dlp"),                     # neither half matches
    ("exec-argument-smuggle", "exec_guard"),      # allowed prefix, no metacharacters
])
def test_known_gap(sid, defense):
    assert t(sid, defense).attack


@pytest.mark.parametrize("sid", ["exfil-reversed-allowed-sink", "misuse-config-overwrite",
                                 "exec-argument-smuggle", "trust-false-assurance", "misuse-amount-inflate"])
def test_layered_residual_gap(sid):
    assert t(sid, "layered").attack


def test_soft_defenses_do_not_change_a_compromised_agent():
    for sc in BY.values():
        for d in ("spotlight", "prompt_guard"):
            assert t(sc.id, d).attack == t(sc.id, "none").attack


@pytest.mark.parametrize("sid,defense", [
    ("ctrl-llm-topic-doc", "injection_filter"),
    ("ctrl-recipient-from-doc", "egress"),
    ("ctrl-secret-to-owner", "dlp"),
    ("ctrl-note-from-doc", "memory_guard"),
    ("ctrl-mail-five", "rate_limit"),
    ("ctrl-tool-update", "tool_pin"),
    ("ctrl-piped-test-log", "exec_guard"),
    ("ctrl-external-image", "output_filter"),
    ("ctrl-important-tag", "manifest_scan"),
])
def test_defense_has_a_measured_false_positive(sid, defense):
    assert t(sid, "none", "benign").utility
    assert not t(sid, defense, "benign").utility


def test_plain_control_survives_the_full_stack():
    assert t("ctrl-two-secrets-plain", "layered", "benign").utility


def test_blocked_call_is_recorded_as_attempted_not_as_success():
    r = t("ipi-doc-polite", "egress")
    assert r.attempted and not r.attack and r.blocked >= 1
    assert any(e["blocked_by"] for e in r.trace)


def test_unknown_defense_fails_loudly():
    with pytest.raises(ValueError):
        make_stack("spotlihgt")


def test_ablations_cover_the_profile():
    ab = ablations("layered")
    assert set(ab) == set(PROFILES["layered"])
    assert all(k not in v.split("+") for k, v in ab.items())
