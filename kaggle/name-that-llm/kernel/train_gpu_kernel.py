"""Kaggle GPU notebook: train one transformer per fold, saved for the offline submission kernel.

Attach the `ntl-source` dataset and a base model snapshot. Save the notebook's output as a dataset,
then point FOLDS_DIR in submission_kernel.py at it. Check that the base model's licence fits the
competition rules first. Never tried on a GPU or on Kaggle: see NOTES.md for what has been tested.
"""
import os
import subprocess
import sys
from glob import glob
from pathlib import Path

BASE_MODEL = "/kaggle/input/your-base-model"  # Set this.
SETTINGS = ["--lora-r", "16", "--epochs", "3", "--batch-size", "4", "--grad-accum", "4",
            "--max-length", "384", "--lr", "1e-4"]  # Starting values, none tuned on real data.

hits = glob("/kaggle/input/**/ntl/__init__.py", recursive=True)
if not hits:
    raise SystemExit("ntl source not found: attach the ntl-source dataset")
source = str(Path(hits[0]).parents[1])
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "peft"], check=False)
subprocess.run([sys.executable, "-m", "ntl.hf_train", "--model", BASE_MODEL,
                "--out", "/kaggle/working/folds", "--save-models", *SETTINGS],
               check=True, env={**os.environ, "PYTHONPATH": source})
