"""Validity of the blind holdout: solvable tasks and live oracles, under no defense only.

This file must never assert how a defense scores on the holdout. See holdout/README.md.
"""

from pathlib import Path

import pytest

from gauntlet.agents import make_agent
from gauntlet.runner import run_trial
from gauntlet.scenario import load_scenarios

ALL = load_scenarios(Path(__file__).parent.parent / "holdout")


def trial(sc, agent):
    return run_trial(sc, lambda: make_agent(agent), "none", 0)


def test_size():
    assert sum(not s.control for s in ALL) == 24 and sum(s.control for s in ALL) == 8


@pytest.mark.parametrize("sc", ALL, ids=lambda s: s.id)
def test_valid(sc):
    t = trial(sc, "benign")
    assert t.utility and not t.attack and t.error is None
    c = trial(sc, "compromised")
    assert c.attack is (not sc.control)
