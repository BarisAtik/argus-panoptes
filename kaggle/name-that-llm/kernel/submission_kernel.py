"""Kaggle offline kernel. Fits on the competition's train.csv at run time, which avoids shipping
a pickle tied to a scikit-learn version, then writes /kaggle/working/submission.parquet.

Attach the `ntl-source` dataset (see scripts/package_source.sh). You push and submit this yourself.
"""
import subprocess
import sys
from glob import glob
from pathlib import Path

MODELS = ["tfidf_lr", "masked_lr"]
USE_ASSIGNMENT = False  # Leave off until NOTES.md's checklist passes on the real test distribution.

hits = glob("/kaggle/input/**/ntl/__init__.py", recursive=True)
if not hits:
    raise SystemExit("ntl source not found: attach the ntl-source dataset to this kernel")
sys.path.insert(0, str(Path(hits[0]).parents[1]))

from ntl.data import KAGGLE_DIR, LABEL, load  # noqa: E402
from ntl.leakage import run_all  # noqa: E402
from ntl.submit import predict_test, validate_submission  # noqa: E402

train, test = load(KAGGLE_DIR)
print(run_all(train, test))  # Lands in the kernel log so you can check test against train.
sub = predict_test(train, test, MODELS, assign=USE_ASSIGNMENT)
validate_submission(sub, test, train[LABEL].unique())
sub.to_parquet("/kaggle/working/submission.parquet", index=False)
print(subprocess.run(["ls", "-la", "/kaggle/working"], capture_output=True, text=True).stdout)
