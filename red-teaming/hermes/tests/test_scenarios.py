import asyncio

import pytest

from hermes.channel import scenario as channel_scenario, trial
from hermes.controls import STACKS, build
from hermes.factorial import attack_cell, attack_cells, control_cells
from hermes.mesh import Mesh
from hermes.runner import matrix, run
from hermes.scenario import load

SURFACE = load()


def test_every_attack_works_with_no_defense():
    bad = [r.scenario for r in matrix(attack_cells() + [s for s in SURFACE if not s.control], ["none"]) if not r.attack]
    assert bad == []


def test_every_control_is_solvable_with_no_defense():
    bad = [r.scenario for r in matrix(control_cells() + [s for s in SURFACE if s.control], ["none"]) if not r.util]
    assert bad == []


def test_no_crashes_anywhere():
    cells = attack_cells()[::9] + control_cells() + SURFACE
    assert [r.crashed for r in matrix(cells, list(STACKS)) if r.crashed] == []


def test_benign_agent_ignores_injection():
    sc = attack_cell("exfil", 2, "verbatim", "attacker", "declared", "hijacked", "none")
    m = Mesh(sc, [], "benign", 0)
    asyncio.run(m.run_task(0))
    assert not any(e.name == "read_secret" for e in m.events)


def test_outcome_does_not_depend_on_seed():
    sc = attack_cell("exfil", 3, "words", "partner", "undeclared", "rogue_relay", "store")
    assert len({(run(sc, "full", s).attack, run(sc, "taint_hwm", s).attack) for s in range(4)}) == 1


def test_hop_zero_keeps_its_trifecta_stop():
    assert not run(attack_cell("exfil", 0, "verbatim", "attacker", "declared", "hijacked", "none"), "agent_trifecta").attack


def test_split_trifecta_walks_past_single_agent_rule():
    assert run(attack_cell("exfil", 1, "verbatim", "attacker", "declared", "hijacked", "none"), "agent_trifecta").attack


def test_rogue_relay_breaks_both_link_based_schemes_but_not_hwm():
    sc = attack_cell("exfil", 3, "verbatim", "partner", "declared", "rogue_relay", "none")
    assert run(sc, "taint_inband").attack and run(sc, "taint_lineage").attack
    assert not run(sc, "taint_hwm").attack


def test_store_launders_past_lineage_but_not_hwm():
    sc = attack_cell("exfil", 2, "verbatim", "attacker", "undeclared", "hijacked", "store")
    assert run(sc, "taint_lineage").attack
    assert not run(sc, "taint_hwm").attack


@pytest.mark.parametrize("stack", ["agent_dlp", "agent_egress", "caps", "taint_hwm", "peer_acl", "full"])
def test_scoring_ignores_blocked_calls(stack):
    sc = attack_cell("exfil", 1, "verbatim", "attacker", "undeclared", "hijacked", "none")
    assert not run(sc, stack).attack


def test_caps_block_an_ungranted_push_callback():
    sc = next(s for s in SURFACE if s.id == "push-callback-exfil")
    assert not run(sc, "caps").attack and not run(sc, "push_guard").attack


def test_signature_alone_does_not_stop_a_lying_signed_card():
    sc = next(s for s in SURFACE if s.id == "skill-shadowing-signed")
    assert run(sc, "card_sig").attack
    assert not run(sc, "card_pin").attack


def test_signature_stops_tampering_and_unsigned_cards():
    for sid in ("card-spoofed-unsigned", "card-tampered-in-transit"):
        sc = next(s for s in SURFACE if s.id == sid)
        assert not run(sc, "card_sig").attack


def test_pin_cannot_tell_an_honest_update_from_a_rug_pull_gap():
    rug = next(s for s in SURFACE if s.id == "card-rug-pull")
    bump = next(s for s in SURFACE if s.id == "surface-ctl-card-version-bump")
    assert not run(rug, "card_pin").attack
    assert not run(bump, "card_pin").util


@pytest.mark.parametrize("sid", ["artifact-injection", "worm-memory", "final-reply-exfil", "rogue-source-clean-context"])
def test_nothing_here_stops_these_gap(sid):
    assert run(next(s for s in SURFACE if s.id == sid), "full").attack


def test_typed_value_inside_range_passes_gap():
    sc = next(s for s in SURFACE if s.id == "typed-amount-tamper")
    assert run(sc, "hwm_typed").attack and not run(sc, "taint_hwm").attack


def test_a_callee_cannot_claim_a_type_it_does_not_match():
    sc = next(s for s in SURFACE if s.id == "surface-ctl-lookup-pay")
    sc.agents["reader"].skills["amount"][-1]["reply"] = "120 and more"
    assert not run(sc, "hwm_typed").util
    sc.agents["reader"].skills["amount"][-1]["reply"] = "120"


def test_rogue_source_with_clean_labels_still_reaches_a_granted_partner_gap():
    sc = attack_cell("exfil", 2, "words", "partner", "undeclared", "rogue_source", "none")
    assert run(sc, "taint_hwm").attack


def test_typed_channel_matches_the_bound_exactly():
    for bits, budget in [(1, None), (1, 16), (2, 4), (4, 8), (8, 4)]:
        r = asyncio.run(trial(bits, budget))
        assert r["leaked"] == r["bound"] == min(64, r["calls"] * bits)


def test_typed_channel_needs_private_declassification():
    sc = channel_scenario(4)
    sc.agents["vault"].outputs["check"]["declass_private"] = False
    from hermes.channel import _SymbolVault, leaked_bits
    m = Mesh(sc, [_SymbolVault(4), *build("taint_hwm+typed_declass")], "compromised", 0)
    asyncio.run(m.run_task(0))
    assert leaked_bits(m, 4) == 0


def test_a_forged_or_stale_cap_is_refused_at_the_gateway():
    from hermes.caps import mint
    from hermes.controls import Caps
    from hermes.core import Msg
    from hermes.mesh import Run
    sc = attack_cell("exfil", 1, "verbatim", "attacker", "declared", "hijacked", "none")
    m = Mesh(sc, build("caps"), "compromised", 0)
    m.set_task(0)
    msg = Msg("a", "b", "work", "x", "c")
    run_ = Run("a", msg, rogue=True)
    assert Caps().on_send(run_, msg, m) == "caps:invalid"  # no token at all
    run_.cap = mint(b"wrong-key-wrong!", "task-0")
    assert Caps().on_send(run_, msg, m) == "caps:invalid"
    run_.cap = mint(m.root, "task-9", ("dests=x",))
    assert Caps().on_send(run_, msg, m) == "caps:stale"
