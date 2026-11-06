"""Pieces added once public reports and a real encoder became available."""
import numpy as np
import pandas as pd
import pytest

from ntl.cv import blend
from ntl.labs import LAB_OF
from ntl.metrics import lab_accuracy
from ntl.proxy import make_split
from ntl.proxy_experiments import thin_prompts
from ntl.submit import align


def test_lab_table_has_all_18_models_and_is_usable():
    assert len(LAB_OF) == 18
    names = list(LAB_OF)
    assert lab_accuracy(names, names, LAB_OF) == 1.0


def test_blend_weights_lean_toward_the_heavier_model():
    a, b = np.array([[0.9, 0.1]]), np.array([[0.2, 0.8]])
    assert blend([a, b], weights=[0.9, 0.1])[0, 0] > blend([a, b])[0, 0]
    assert np.allclose(blend([a, a], weights=[0.2, 0.8]), a)


def test_align_reorders_columns_and_refuses_other_labels():
    classes = np.array(["a", "b"])
    assert np.allclose(align(np.array([[0.3, 0.7]]), ["b", "a"], classes), [[0.7, 0.3]])
    with pytest.raises(ValueError):
        align(np.array([[0.3, 0.7]]), ["b", "c"], classes)


def test_thinning_keeps_at_most_k_distinct_authors_per_prompt():
    frame = pd.DataFrame({"prompt_id": np.repeat(range(30), 7),
                          "model": list("abcdefg") * 30, "text": "x"})
    out = thin_prompts(frame, 3, 0)
    sizes = out.groupby("prompt_id")["model"].nunique()
    assert sizes.max() <= 3 and sizes.min() >= 1 and out["prompt_id"].nunique() == 30


def test_partial_cache_is_refused_rather_than_built():
    grid = pd.DataFrame({"genre": "wp", "num": range(500), "model": "claude",
                         "text": ["word " * 60] * 500})
    with pytest.raises(ValueError, match="partial cache"):
        make_split(grid, 150, 220, 0)
