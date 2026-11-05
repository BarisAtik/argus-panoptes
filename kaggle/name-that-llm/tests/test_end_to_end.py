import subprocess
import sys

import pandas as pd
import pytest

from ntl import synth
from ntl.cv import blend, oof_proba
from ntl.data import LABEL
from ntl.failure import report
from ntl.models import REGISTRY
from ntl.splits import grouped_folds
from ntl.submit import predict_test, validate_submission


def test_submission_contract(small):
    train, test, _ = small
    sub = predict_test(train, test, ["style_lr"])
    validate_submission(sub, test, train[LABEL].unique())
    assert len(sub) == len(test)


@pytest.mark.parametrize("mutate", [
    lambda s: s.rename(columns={"model": "label"}),
    lambda s: s.iloc[:-1],
    lambda s: s.assign(model="nonsense"),
    lambda s: pd.concat([s.iloc[:-1], s.iloc[[0]]]),
    lambda s: s.assign(model=None),
])
def test_validator_rejects_bad_files(small, mutate):
    train, test, _ = small
    sub = pd.DataFrame({"id": test["id"], "model": train[LABEL].iloc[0]})
    with pytest.raises(ValueError):
        validate_submission(mutate(sub), test, train[LABEL].unique())


def test_oof_failure_report_runs(small):
    import numpy as np

    train, _, _ = small
    classes = np.array(sorted(train[LABEL].unique()))
    folds = grouped_folds(train, 3)
    p = oof_proba(REGISTRY["style_lr"](), train, folds, classes)
    assert p.shape == (len(train), 18) and np.allclose(p.sum(axis=1), 1)
    frame = pd.DataFrame(p, columns=classes)
    frame.insert(0, "id", train["id"])
    frame.insert(1, "fold", folds)
    frame.insert(2, "model", train["model"])
    frame.insert(3, "prompt_id", train["prompt_id"])
    assert "Top confusions" in report(frame, train)


def test_blend_is_a_distribution():
    import numpy as np

    a = np.array([[0.9, 0.1]])
    b = np.array([[0.5, 0.5]])
    out = blend([a, b])
    assert np.isclose(out.sum(), 1) and out[0, 0] > 0.5


def test_cli_roundtrip(tmp_path):
    data = tmp_path / "d"
    run = lambda *a: subprocess.run([sys.executable, "-m", *a], check=True,  # noqa: E731
                                    capture_output=True, text=True)
    run("ntl.synth", "--out", str(data), "--prompts", "12", "--test-prompts", "4")
    run("ntl.cv", "--data", str(data), "--out", str(tmp_path / "a"), "--models", "style_lr",
        "--folds", "3", "--no-leakage")
    assert (tmp_path / "a" / "metrics.json").exists()
    sub = tmp_path / "s.parquet"
    run("ntl.submit", "--data", str(data), "--out", str(sub), "--models", "style_lr")
    assert len(pd.read_parquet(sub)) == 4 * 18
    assert synth.model_names()["alpha-1"] == "alpha"
