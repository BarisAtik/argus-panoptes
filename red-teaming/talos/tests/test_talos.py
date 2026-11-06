import random

import torch

from talos import world as W
from talos.model import Talos
from talos.study import model_grid
from talos.study import test_set as fixed_test_set
from talos.tok import STOI, Slots
from talos.train import Config, batch, fit, outcome, predict


def words_of(ex):
    return (ex.user + " " + ex.data + " " + ex.target).split()


def is_entity(w):
    return any(c.isdigit() for c in w) or "@" in w


def test_every_template_word_is_in_the_vocabulary():
    rng = random.Random(1)
    gens = [lambda: W.direct(rng), lambda: W.mention(rng)]
    for f in W.FAMILIES:
        gens += [lambda f=f: W.injected(rng, f, hop=2), lambda f=f: W.delegate(rng, family=f, hop=2)]
    for g in gens:
        for _ in range(300):
            for w in words_of(g()):
                assert w in STOI or is_entity(w), w


def test_targets_parse_and_entities_are_in_the_prompt():
    rng = random.Random(2)
    for _ in range(500):
        ex = W.train_example(rng, "adv")
        assert W.parse_action(ex.target)
        prompt = {w for w, _ in W.render(ex, "plain", rng)}
        assert all(w in STOI or w in prompt for w in ex.target.split())


def test_attack_never_equals_task_and_oracle_fires():
    rng = random.Random(3)
    for f in W.FAMILIES:
        ex = W.injected(rng, f)
        assert outcome(ex, ex.target)["attack"] == 0 and outcome(ex, ex.target)["task"] == 1
        bad = f"call send_email to {ex.attack_dest} body key"
        assert outcome(ex, bad) == {"task": 0, "malformed": 0, "attack": 1}
        assert outcome(ex, "garbled words")["malformed"] == 1


def test_only_segment_can_tell_the_forged_turn_apart():
    rng = random.Random(4)
    ex = W.injected(rng, "break")
    rendered = W.render(ex, "segment", rng)
    data = [w for w, r in rendered if r == 1]
    assert "user" in data and "end" in data  # forged words carry the data role, whatever they spell
    assert {r for w, r in rendered if w == "assistant"} == {0}


def test_salted_nonce_differs_per_trial():
    rng = random.Random(5)
    ex = W.direct(rng)
    a = W.render(ex, "salted", rng)
    b = W.render(ex, "salted", rng)
    assert a != b


def test_slots_round_trip_and_shuffle():
    s = Slots(random.Random(1))
    i = s.encode("x1@corp.test")
    assert s.encode("x1@corp.test") == i and s.decode(i) == "x1@corp.test"
    assert s.encode("the") == STOI["the"]


def test_loss_is_on_the_action_only():
    x, r, y = batch(random.Random(0), Config(batch=4))
    assert x.shape == y.shape == r.shape
    assert ((y != 0).sum(1) < 12).all()


def test_causal_future_does_not_change_past_logits():
    m = Talos(d=32, layers=2, heads=2, max_len=20).eval()
    a = torch.randint(2, 50, (1, 10))
    b = a.clone()
    b[0, 9] = 60
    assert torch.allclose(m(a)[0, :9], m(b)[0, :9])


def test_role_embedding_is_off_unless_segment():
    assert Talos(d=32, layers=1, heads=2).role is None
    assert Talos(d=32, layers=1, heads=2, roles=True).role is not None


def test_small_model_learns_direct_tasks():
    c = Config(regime="clean", prov="plain", d=64, layers=2, steps=500, batch=32, lr=3e-3)
    m = fit(c)
    rng = random.Random(9)
    exs = [W.direct(rng, "z", "open") for _ in range(50)]
    hits = sum(t == e.target for t, e in zip(predict(m, exs, "plain"), exs))
    assert hits >= 30  # copies a name it never saw in training


def test_grid_is_the_preregistered_size():
    g = model_grid()
    assert len(g) == 60
    assert sum(c.regime == "adv" for c in g) == 28


def test_test_set_is_fixed_and_uses_unseen_names():
    a = [e.user for _, e in fixed_test_set(5)]
    b = [e.user for _, e in fixed_test_set(5)]
    assert a == b
    assert any("z" in u for u in a)
