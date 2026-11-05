"""Score the frozen final model on the mcp-lens corpora, which it never trained on.

mcp-lens labels are about poisoned tool descriptions, a task the model was not built for,
so this measures transfer. The threshold stays the one set on third-party validation data.
"""

import json
import sys
from pathlib import Path

import numpy as np

from tripwire import metrics as M
from tripwire.infer import Detector

corpus = Path(__file__).resolve().parents[2] / "mcp-lens" / "corpus"
det = Detector.load()
out = {}
for name in ("dev", "dev2", "holdout"):
    rows = [json.loads(l) for l in (corpus / f"{name}.jsonl").read_text().splitlines() if l.strip()]
    y = np.array([r["label"] for r in rows])
    s = det.score([r["description"] for r in rows])
    out[name] = {"n": len(y), "positives": int(y.sum()), "auroc": M.auroc(y, s), **M.rates(y, s, det.threshold)}
Path("reports/external-mcp-lens.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
sys.exit(0)
