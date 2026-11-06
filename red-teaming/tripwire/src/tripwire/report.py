"""Write reports/experiment.md from reports/experiment.json, and robustness.json if present."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

MODELS = ("regex", "tfidf_lr", "byte_cnn")


def _mean(rows, model, key):
    v = [r[model][key] for r in rows if key in r.get(model, {})]
    return float(np.nanmean(v)) if v else float("nan")


def _p(x: float) -> str:
    return "n/a" if x != x else f"{x:.1%}"


def regime_table(res: dict) -> list[str]:
    out = ["| Split | Model | AUROC | Recall at threshold | FPR at threshold | Recall at 1% FPR (oracle) |", "| --- | --- | ---: | ---: | ---: | ---: |"]
    labels = {"naive": "naive (shared templates)", "bare": "bare payloads in training", "grouped": "grouped templates",
              "leave_source_out": "leave one source out"}
    for key, label in labels.items():
        for m in MODELS:
            rows = res[key]
            out.append(f"| {label} | {m} | {_mean(rows, m, 'auroc'):.3f} | {_p(_mean(rows, m, 'recall'))} | {_p(_mean(rows, m, 'fpr'))} | {_p(_mean(rows, m, 'recall_at_1pct_fpr'))} |")
    return out


def source_tables(res: dict) -> list[str]:
    by_pos, by_neg = defaultdict(list), defaultdict(list)
    for r in res["leave_source_out"]:
        by_pos[r["pos_out"]].append(r)
        by_neg[r["neg_out"]].append(r)
    out = ["| Held-out attack source | CNN recall | CNN FPR | TF-IDF recall | TF-IDF FPR | Regex recall |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    out += [f"| {k} | {_p(_mean(v, 'byte_cnn', 'recall'))} | {_p(_mean(v, 'byte_cnn', 'fpr'))} | {_p(_mean(v, 'tfidf_lr', 'recall'))} | {_p(_mean(v, 'tfidf_lr', 'fpr'))} | {_p(_mean(v, 'regex', 'recall'))} |"
            for k, v in sorted(by_pos.items())]
    out += ["", "| Held-out benign source | CNN recall | CNN FPR | TF-IDF recall | TF-IDF FPR |", "| --- | ---: | ---: | ---: | ---: |"]
    out += [f"| {k} | {_p(_mean(v, 'byte_cnn', 'recall'))} | {_p(_mean(v, 'byte_cnn', 'fpr'))} | {_p(_mean(v, 'tfidf_lr', 'recall'))} | {_p(_mean(v, 'tfidf_lr', 'fpr'))} |"
            for k, v in sorted(by_neg.items())]
    return out


def robustness_tables(rob: dict) -> list[str]:
    s = rob["summary"]
    names = list(next(iter(s.values())))
    out = ["| Detector | " + " | ".join(names) + " |", "| --- |" + " ---: |" * len(names)]
    out += ["| " + k + " | " + " | ".join(f"{v[n]['recall']:.0%}" for n in names) + " |" for k, v in s.items()]
    out += ["", "False-positive rate when the same rewrite is applied to benign documents:", "",
            "| Detector | " + " | ".join(names) + " |", "| --- |" + " ---: |" * len(names)]
    out += ["| " + k + " | " + " | ".join(f"{v[n]['fpr']:.1%}" for n in names) + " |" for k, v in s.items()]
    return out


def main() -> int:
    res = json.loads(Path("reports/experiment.json").read_text())
    a = res["audit"]
    md = ["# Tripwire experiment", "",
          f"Generated from `experiment.json`. {res['params']['seeds']} seeds, {res['params']['n']} positive training documents. "
          "Thresholds come from validation data in the training sources, aiming for 1% FPR. "
          "Numbers are means over seeds. Per-seed values and template-bootstrap intervals are in the JSON.", "",
          "## Data audit", "",
          f"- {a['payloads']} payloads, {a['unique_payload_texts']} unique, from only **{a['templates']} templates**, so the effective sample is far smaller than the document count.",
          f"- In a naive random split, {a['naive_split_leak']['payload_seen']:.1%} of positive test documents carry a payload that also appears in training.",
          f"- The regex fires on {max(a['regex_hits_on_benign_by_source'].values()):.1%} of benign text in every source, so its false positives are not the problem. Its recall is.", "",
          "## By split", "", *regime_table(res), "", "## By held-out source", "", *source_tables(res), ""]
    rp = Path("reports/robustness.json")
    if rp.exists():
        rob = json.loads(rp.read_text())
        md += ["## Recall under rewriting", "",
               f"{rob['params']['seeds']} seeds, grouped splits, threshold fixed on clean validation data. "
               f"Augmented models trained on {', '.join(rob['params']['seen'])}. Never trained on: {', '.join(rob['params']['unseen'])}.", "",
               *robustness_tables(rob), ""]
    Path("reports/experiment.md").write_text("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
