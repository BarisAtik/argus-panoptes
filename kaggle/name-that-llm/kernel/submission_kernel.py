"""Kaggle offline kernel. Fits on the competition's train.csv at run time, which avoids shipping
a pickle tied to a scikit-learn version, then writes /kaggle/working/submission.parquet.

Attach the `ntl-source` dataset (see scripts/package_source.sh). You push and submit this yourself.
"""
import subprocess
import sys
from glob import glob
from pathlib import Path

MODELS = ["tfidf_lr", "masked_lr"]
USE_ASSIGNMENT = False  # Public reports: test prompts aren't complete, and this lowers the score.
USE_BALANCE = False  # Turn on only if the adversarial AUC in the log shows shift. See NOTES.md.
# Attach the output of kernel/train_gpu_kernel.py and the base model as datasets, then set both.
# Leave them None for the CPU-only baseline. Scoring sees the real test only inside this rerun, so
# transformer inference has to happen here, offline, within the time limit.
FOLDS_DIR = None  # "/kaggle/input/ntl-folds"
BASE_MODEL = None  # "/kaggle/input/your-base-model"; only LoRA folds need it
TRANSFORMER_WEIGHT = 1 / 3  # Equal thirds is what the proxy tested. Change only by nested CV.
MAX_LENGTH, BATCH_SIZE = 384, 8

hits = glob("/kaggle/input/**/ntl/__init__.py", recursive=True)
if not hits:
    raise SystemExit("ntl source not found: attach the ntl-source dataset to this kernel")
sys.path.insert(0, str(Path(hits[0]).parents[1]))

from ntl.data import KAGGLE_DIR, LABEL, load  # noqa: E402
from ntl.leakage import run_all  # noqa: E402
from ntl.submit import predict_test, validate_submission  # noqa: E402

train, test = load(KAGGLE_DIR)
print(run_all(train, test))  # Lands in the kernel log so you can check test against train.
extra = None
if FOLDS_DIR:
    from argparse import Namespace

    import torch

    from ntl.hf_train import load_tokenizer, predict_folds

    device = "cuda" if torch.cuda.is_available() else "cpu"
    settings = Namespace(max_length=MAX_LENGTH, batch_size=BATCH_SIZE)
    tokenizer = load_tokenizer(BASE_MODEL or FOLDS_DIR + "/fold0")
    extra = predict_folds(FOLDS_DIR, BASE_MODEL, test["text"].tolist(), settings, device, tokenizer)
sub = predict_test(train, test, MODELS, assign=USE_ASSIGNMENT, balance=USE_BALANCE, extra=extra,
                   extra_weight=TRANSFORMER_WEIGHT)
validate_submission(sub, test, train[LABEL].unique())
sub.to_parquet("/kaggle/working/submission.parquet", index=False)
print(subprocess.run(["ls", "-la", "/kaggle/working"], capture_output=True, text=True).stdout)
