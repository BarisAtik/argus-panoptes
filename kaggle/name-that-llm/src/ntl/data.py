"""Loading, schema checks and the structural facts the whole validation design rests on."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ID, PROMPT, TEXT, LABEL = "id", "prompt_id", "text", "model"
TRAIN_COLS = (ID, PROMPT, TEXT, LABEL)
TEST_COLS = (ID, TEXT)
N_MODELS = 18  # stated by the competition; checked against the data, not assumed downstream
KAGGLE_DIR = Path("/kaggle/input/competitions/name-that-llm")


def find_data_dir(explicit: str | Path | None = None) -> Path:
    """Explicit path > Kaggle's mount > local data/raw."""
    for candidate in (explicit, KAGGLE_DIR, Path("data/raw")):
        if candidate is not None and Path(candidate, "train.csv").exists():
            return Path(candidate)
    raise FileNotFoundError(
        "train.csv not found. Run scripts/download_data.sh, or `python -m ntl.synth` for fake data."
    )


def _check_columns(df: pd.DataFrame, cols: tuple[str, ...], name: str) -> None:
    missing = set(cols) - set(df.columns)
    if missing:
        raise ValueError(f"{name} is missing columns {sorted(missing)}; has {list(df.columns)}")
    if df[ID].duplicated().any():
        raise ValueError(f"{name} has duplicate ids")
    if df[TEXT].isna().any():
        raise ValueError(f"{name} has null text")


def load(data_dir: str | Path | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    d = find_data_dir(data_dir)
    train, test = pd.read_csv(d / "train.csv"), pd.read_csv(d / "test.csv")
    _check_columns(train, TRAIN_COLS, "train")
    _check_columns(test, TEST_COLS, "test")
    return train, test


@dataclass(frozen=True)
class GridReport:
    """How close train is to a complete prompt x model grid.

    2,699 rows / 150 prompts is almost exactly 18 per prompt, which suggests every model answered
    every prompt. That single fact drives two decisions: folds must keep prompts whole, and
    `assign.py` can treat "one prompt, each model once" as a constraint. So it gets measured here.
    """

    n_rows: int
    n_prompts: int
    n_models: int
    median_rows_per_prompt: float
    share_prompts_complete: float
    share_prompts_with_repeat_model: float

    @property
    def is_grid(self) -> bool:
        return self.share_prompts_complete > 0.9 and self.share_prompts_with_repeat_model < 0.05


def grid_report(train: pd.DataFrame) -> GridReport:
    per = train.groupby(PROMPT)[LABEL].agg(["size", "nunique"])
    n_models = train[LABEL].nunique()
    return GridReport(
        n_rows=len(train),
        n_prompts=len(per),
        n_models=n_models,
        median_rows_per_prompt=float(per["size"].median()),
        share_prompts_complete=float((per["nunique"] == n_models).mean()),
        share_prompts_with_repeat_model=float((per["size"] > per["nunique"]).mean()),
    )


def word_count(text: pd.Series) -> np.ndarray:
    return text.str.split().str.len().to_numpy()
