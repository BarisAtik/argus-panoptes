"""The scoring path for the second blind holdout, tried on the first holdout file. Nothing here touches reports/."""

import json
import subprocess
from pathlib import Path

import pytest

from hermes.cli import main
from hermes.controls import STACKS
from hermes.holdout import STACKS_2, score

ROOT = Path(__file__).parent.parent
FIRST = ROOT / "holdout" / "05_blind_controls.yaml"
NEW = {"taint_inferred", "inferred_typed", "full_inferred", "hwm_typed_fwd", "lineage_typed_fwd", "inferred_typed_fwd",
       "full_fwd", "full_lineage_fwd", "full_inferred_fwd"}


def test_the_named_stacks_are_all_scored():
    assert set(STACKS_2) == {"none", "caps", "identity", "full", "full_lineage"} | NEW
    assert set(STACKS_2) <= set(STACKS)


def test_scores_a_parameterised_path_and_writes_both_reports(tmp_path):
    assert main(["holdout2", "--path", str(FIRST), "--out", str(tmp_path)]) == 0
    res = json.loads((tmp_path / "holdout2.json").read_text())
    assert list(res["stacks"]) == STACKS_2
    assert res["stacks"]["none"]["utility"] == [16, 16] and res["crashes"] == [] and res["baseline_unsolved"] == []
    text = (tmp_path / "holdout2.md").read_text()
    assert "33a516c" in text and "Agents declaring an `input` type in this file: 0" in text


def test_scored_once(tmp_path):
    main(["holdout2", "--path", str(FIRST), "--out", str(tmp_path)])
    with pytest.raises(SystemExit):
        main(["holdout2", "--path", str(FIRST), "--out", str(tmp_path)])


def test_a_missing_file_says_so(tmp_path):
    with pytest.raises(SystemExit):
        main(["holdout2", "--path", str(tmp_path / "no.yaml"), "--out", str(tmp_path)])


def test_the_first_holdout_still_scores_as_published(tmp_path):
    score(FIRST, tmp_path)
    assert json.loads((tmp_path / "holdout.json").read_text()) == json.loads((ROOT / "reports" / "holdout.json").read_text())


def test_make_target_points_at_the_second_file():
    out = subprocess.run(["make", "-n", "holdout2"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    assert "holdout2 --path holdout/06_blind_controls_2.yaml --out reports" in out
