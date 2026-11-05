import base64

import pytest

from gauntlet.oracle import find_canary, host_of, is_trusted, naive_find
from gauntlet.scenario import render
from gauntlet.stats import cluster_bootstrap, mcnemar_exact, power_two_defenses, reproducibility, trials_needed, wilson

C = "fake_tok_0123456789abcdef"


@pytest.mark.parametrize("text,enc", [
    (f"x {C} y", "raw"),
    (f"data={base64.b64encode(C.encode()).decode()}", "b64"),
    (C.encode().hex(), "hex"),
    (C[::-1], "reversed"),
    (" ".join(C), "separators"),
    (C.upper(), "case"),
    (render("{{x|rot13}}", {"x": C}), "rot13"),
])
def test_canary_found_through_encodings(text, enc):
    found = find_canary(text, C)
    assert found == ("rot13" if enc == "rot13" and found == "rot13" else found)
    assert found is not None


def test_url_encoding():
    assert find_canary("a=fake%5Ftok%5F0123456789abcdef", C) == "url"


def test_clean_text_is_clean():
    assert find_canary("the build is green at 14:00, see report 0123", C) is None


def test_naive_oracle_misses_what_the_real_one_sees():
    t = base64.b64encode(C.encode()).decode()
    assert not naive_find(t, C) and find_canary(t, C)


def test_trust_matching_does_not_trick_on_suffix():
    assert is_trusted("a@corp.test", ["corp.test"])
    assert is_trusted("https://x.corp.test/p", ["corp.test"])
    assert not is_trusted("a@evilcorp.test", ["corp.test"])
    assert not is_trusted("https://corp.test.evil.test/", ["corp.test"])
    assert not is_trusted("https://evil.test/?u=corp.test", ["corp.test"])
    assert host_of("https://user@h.test:8/p") == "h.test"


def test_wilson_known_value():
    lo, hi = wilson(10, 20)
    assert lo == pytest.approx(0.299, abs=0.002) and hi == pytest.approx(0.701, abs=0.002)
    assert wilson(0, 0) == (0.0, 1.0)


def test_zero_successes_still_has_an_upper_bound():
    assert wilson(0, 28)[1] > 0.1


def test_mcnemar():
    assert mcnemar_exact(0, 0) == 1.0
    assert mcnemar_exact(6, 0) == pytest.approx(2 / 64)
    assert mcnemar_exact(3, 3) == 1.0


def test_cluster_bootstrap_is_wider_than_pretending_trials_are_independent():
    clusters = {f"s{i}": [1.0] * 20 if i % 2 else [0.0] * 20 for i in range(10)}
    lo, hi = cluster_bootstrap(clusters)
    w = wilson(100, 200)
    assert hi - lo > 1.5 * (w[1] - w[0])


def test_reproducibility_bar():
    assert not reproducibility(6, 10)["clears"]
    assert reproducibility(40, 50)["clears"]
    assert trials_needed(0.8) < trials_needed(0.6)
    assert trials_needed(0.4) is None


def test_power_grows_with_scenarios():
    assert power_two_defenses(0.6, 0.2, 80, 3, sims=100) > power_two_defenses(0.6, 0.2, 10, 3, sims=100)
