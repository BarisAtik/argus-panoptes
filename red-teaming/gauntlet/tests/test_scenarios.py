"""Validity of the benchmark itself. A benchmark with dead oracles reports safety it never tested."""

import pytest

from gauntlet.agents import make_agent
from gauntlet.runner import run_trial
from gauntlet.scenario import CATEGORIES, load_scenarios

ALL = load_scenarios()
ATTACKS = [s for s in ALL if not s.control]
CONTROLS = [s for s in ALL if s.control]
ids = lambda s: s.id


def trial(sc, agent="benign", defense="none", seed=0):
    return run_trial(sc, lambda: make_agent(agent), defense, seed)


def test_every_category_is_covered():
    assert {s.category for s in ATTACKS} == set(CATEGORIES)
    assert len(CONTROLS) >= 10


@pytest.mark.parametrize("sc", ALL, ids=ids)
def test_task_is_solvable_and_clean(sc):
    t = trial(sc)
    assert t.utility, t.reasons
    assert not t.attack and not t.attempted
    assert t.error is None


@pytest.mark.parametrize("sc", ATTACKS, ids=ids)
def test_attack_oracle_is_alive(sc):
    t = trial(sc, "compromised")
    assert t.attack, f"{sc.id}: oracle never fires, the scenario cannot detect anything"


@pytest.mark.parametrize("sc", CONTROLS, ids=ids)
def test_control_never_fires(sc):
    t = trial(sc, "compromised")
    assert not t.attack and t.utility


@pytest.mark.parametrize("sc", ALL, ids=ids)
def test_only_reserved_names_and_no_real_targets(sc):
    import json
    import re

    blob = json.dumps(sc.world) + " ".join(s.task for s in sc.sessions)
    for host in re.findall(r"https?://([^/\s\"\\]+)", blob) + re.findall(r"@([a-z0-9.-]+\.[a-z]+)", blob):
        assert host.endswith(".test"), host


def test_canary_differs_by_seed_and_is_stable_for_a_seed():
    sc = next(s for s in ATTACKS if s.id == "ipi-email-blunt")
    a, b, c = (trial(sc, "compromised", seed=s).trace for s in (1, 1, 2))
    assert a == b
    assert a != c


def test_stage_runs_once_across_sessions():
    sc = next(s for s in ATTACKS if s.id == "mem-two-session")
    t = trial(sc, "compromised")
    assert sum(e["tool"] == "remember" for e in t.trace) == 1
