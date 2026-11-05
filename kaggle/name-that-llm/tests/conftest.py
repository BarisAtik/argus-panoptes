import pytest

from ntl import synth


@pytest.fixture(scope="session")
def small():
    """Small fake competition: (train, test, truth)."""
    return synth.make(n_prompts=30, n_test_prompts=10, seed=3)
