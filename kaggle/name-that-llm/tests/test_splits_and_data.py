import numpy as np
import pandas as pd
import pytest

from ntl.data import LABEL, PROMPT, TEXT, grid_report
from ntl.splits import assert_no_group_overlap, grouped_folds, random_folds


def test_grid_detected(small):
    train, _, _ = small
    report = grid_report(train)
    assert report.n_models == 18
    assert report.is_grid
    assert report.median_rows_per_prompt == 18


def test_grid_rejects_repeated_authors(small):
    train, _, _ = small
    broken = train.copy()
    broken[LABEL] = broken[LABEL].sample(frac=1, random_state=0).to_numpy()
    assert not grid_report(broken).is_grid


def test_grouped_folds_keep_prompts_whole(small):
    train, _, _ = small
    folds = grouped_folds(train, 5)
    assert train.assign(f=folds).groupby(PROMPT)["f"].nunique().max() == 1
    assert set(folds) == set(range(5))


def test_random_folds_do_split_prompts(small):
    """Guards the comparison: if this stopped being true the 'wrong' scheme would prove nothing."""
    train, _, _ = small
    folds = random_folds(train, 5)
    with pytest.raises(AssertionError):
        assert_no_group_overlap(folds, train[PROMPT].to_numpy())


def test_overlap_check_flags_unassigned_rows():
    with pytest.raises(AssertionError):
        assert_no_group_overlap(np.array([0, -1]), np.array(["a", "b"]))


def test_synth_has_competition_shape(small):
    train, test, truth = small
    assert list(train.columns) == ["id", "prompt_id", "text", "model"]
    assert list(test.columns) == ["id", "text"]
    assert not set(train[PROMPT]) & set(truth[PROMPT])
    words = pd.concat([train, test])[TEXT].str.split().str.len()
    assert words.min() >= 30
