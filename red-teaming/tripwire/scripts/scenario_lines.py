"""Post-hoc diagnostic: why did the detector stop so little in the Gauntlet?

Scores each line of the mock worlds, labelling a line positive when it carries a scenario's
attack marker. Separates "no signal" from "signal, wrong threshold". Labels are rough, since
a marker is only one phrase of a payload. Nothing here is used for training or tuning.
"""

import json
from pathlib import Path

import numpy as np
import yaml

from tripwire import metrics as M
from tripwire.infer import Detector

root = Path(__file__).resolve().parents[2] / "gauntlet"
det = Detector.load()


def strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from strings(v)


out = {}
for name, folder in (("dev", root / "src/gauntlet/scenarios"), ("holdout", root / "holdout")):
    lines, y, whole, wy = [], [], [], []
    for f in sorted(folder.glob("*.yaml")):
        for sc in yaml.safe_load(f.read_text()):
            markers = [s.get("marker", "") for s in (sc.get("attack") or {}).get("stages", [])]
            texts = list(strings(sc.get("world", {})))
            hits = 0
            for t in texts:
                for line in filter(str.strip, t.split("\n")):
                    pos = any(m and m in line for m in markers)
                    hits += pos
                    lines.append(line)
                    y.append(int(pos))
            if not sc.get("control"):
                whole.append("\n".join(texts))
                wy.append(1)
            else:
                whole.append("\n".join(texts))
                wy.append(0)
    y, wy = np.array(y), np.array(wy)
    s, ws = det.score(lines), det.score(whole)
    out[name] = {"lines": len(y), "positive_lines": int(y.sum()), "line_auroc": M.auroc(y, s),
                 "line_recall_at_frozen_threshold": M.rates(y, s, det.threshold)["recall"], "line_fpr_at_frozen_threshold": M.rates(y, s, det.threshold)["fpr"],
                 "line_recall_at_local_1pct_fpr": M.recall_at_fpr(y, s, 0.01), "line_recall_at_local_10pct_fpr": M.recall_at_fpr(y, s, 0.10),
                 "scenario_auroc": M.auroc(wy, ws), "scenario_recall_at_frozen_threshold": M.rates(wy, ws, det.threshold)["recall"],
                 "scenario_fpr_at_frozen_threshold": M.rates(wy, ws, det.threshold)["fpr"]}
Path("reports/scenario-lines.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
