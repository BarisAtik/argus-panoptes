"""Offline checks for the real-text proxy: a tiny fake cache stands in for the download."""
import numpy as np
import pandas as pd
import pytest

from ntl import proxy
from ntl.assign import assign_within_clusters, balance_classes
from ntl.splits import assert_no_group_overlap, topic_folds


@pytest.fixture()
def cache(tmp_path):
    rng = np.random.default_rng(0)
    for genre in ("wp", "essay"):
        for author in proxy.AUTHORS:
            folder = tmp_path / genre / author
            folder.mkdir(parents=True)
            for i in range(1, 21):
                n = 300 if not (author == "gpt" and i == 3) else 10  # one text too short to use
                (folder / f"{i}.txt").write_text(" ".join(rng.choice(["a", "b", "c"], n)))
    return tmp_path


def test_grid_reader_and_short_text_filter(cache):
    grid = proxy.read_grid(cache)
    assert len(grid) == 2 * 7 * 20
    cut = proxy.cut_passages(grid)
    assert len(cut) == len(grid) - 2
    lengths = cut["text"].str.split().str.len()
    assert lengths.between(proxy.MIN_WORDS, proxy.MAX_WORDS).all()


def test_cut_length_does_not_depend_on_author(cache):
    cut = proxy.cut_passages(proxy.read_grid(cache))
    means = cut.assign(n=cut["text"].str.split().str.len()).groupby("model")["n"].mean()
    assert means.max() - means.min() < 40  # sampling noise only; raw texts are all 300 words


def test_split_keeps_prompts_disjoint_and_complete(cache):
    train, test = proxy.make_split(proxy.read_grid(cache), 10, 8)
    assert not set(train["prompt_id"]) & set(test["prompt_id"])
    assert train["prompt_id"].nunique() == 10 and test["prompt_id"].nunique() == 8
    assert (train.groupby("prompt_id")["model"].nunique() == 7).all()
    assert "wp_3" not in set(train["prompt_id"]) | set(test["prompt_id"])  # incomplete prompt


def test_split_is_reproducible_and_ids_hide_order(cache):
    a, _ = proxy.make_split(proxy.read_grid(cache), 10, 8, seed=1)
    b, _ = proxy.make_split(proxy.read_grid(cache), 10, 8, seed=1)
    pd.testing.assert_frame_equal(a, b)
    assert sorted(a["id"]) == list(range(len(a)))


def test_write_comp_keeps_labels_out_of_test(cache, tmp_path):
    train, test = proxy.make_split(proxy.read_grid(cache), 10, 8)
    proxy.write_comp(train, test, tmp_path / "comp")
    assert list(pd.read_csv(tmp_path / "comp" / "test.csv").columns) == ["id", "text"]


def test_balance_evens_out_a_shy_class():
    rng = np.random.default_rng(0)
    y = np.repeat(np.arange(3), 300)
    logits = rng.normal(size=(900, 3)) + np.eye(3)[y] * 1.5
    logits[:, 0] -= 2.0  # class 0 is under-predicted
    p = np.exp(logits) / np.exp(logits).sum(axis=1, keepdims=True)
    balanced = balance_classes(p)
    assert (p.argmax(1) == 0).mean() < 0.1
    assert abs((balanced.argmax(1) == 0).mean() - 1 / 3) < 0.05
    assert balanced.mean(axis=0) == pytest.approx(np.full(3, 1 / 3), abs=1e-3)
    assert balanced.sum(axis=1) == pytest.approx(np.ones(900))


def test_full_cluster_rule_skips_partial_clusters():
    p = np.array([[.9, .1, 0], [.8, .2, 0], [.1, .8, .1], [.1, .1, .8], [.7, .2, .1]])
    clusters = np.array([0, 0, 1, 1, 1])
    assert assign_within_clusters(p, clusters, min_size=3)[:2].tolist() == [0, 0]
    assert sorted(assign_within_clusters(p, clusters, min_size=3)[2:]) == [0, 1, 2]


def test_topic_folds_keep_prompts_and_topics_apart(small):
    train = small[0]
    folds = topic_folds(train, 3, 6)
    assert_no_group_overlap(folds, train["prompt_id"].to_numpy())
    assert set(folds) == {0, 1, 2}
