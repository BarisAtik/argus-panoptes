"""Everything we report about a classifier, computed the same way for every model."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np

from forge.calibration import (
    brier,
    ece,
    fit_temperature,
    nll,
    probabilities,
    reliability_table,
    risk_at,
    risk_coverage,
)
from forge.report import markdown_table, run_metadata, write_report
from forge.stats import mcnemar_exact, mean_ci
from text_nl import behaviour
from text_nl.audit import canonical, language_guess, tokens
from text_nl.perturb import PERTURBATIONS

Predict = Callable[[list[str]], np.ndarray]


def f1_macro(labels: np.ndarray, predictions: np.ndarray) -> float:
    scores = []
    for cls in np.unique(labels):
        tp = np.sum((predictions == cls) & (labels == cls))
        fp = np.sum((predictions == cls) & (labels != cls))
        fn = np.sum((predictions != cls) & (labels == cls))
        scores.append(2 * tp / max(1, 2 * tp + fp + fn))
    return float(np.mean(scores))


def _row(name: str, correct: np.ndarray, groups=None) -> dict:
    interval = mean_ci(correct.astype(float), groups)
    return {"subset": name, "n": len(correct), "accuracy": interval.estimate,
            "low": interval.low, "high": interval.high}


def slices(texts: list[str], labels: np.ndarray, correct: np.ndarray, leaked: set[int]) -> list:
    lengths = np.array([len(tokens(t)) for t in texts])
    edges = np.quantile(lengths, [0.25, 0.5, 0.75])
    bucket = np.digitize(lengths, edges, right=True)
    rows = []
    for index, name in enumerate(["shortest 25%", "25-50%", "50-75%", "longest 25%"]):
        mask = bucket == index
        if mask.any():
            rows.append(_row(f"length: {name}", correct[mask]))
    for cls, name in enumerate(("negative reviews", "positive reviews")):
        mask = labels == cls
        if mask.any():
            rows.append(_row(name, correct[mask]))
    languages = np.array([language_guess(t) for t in texts])
    for language in ("en", "unclear"):
        mask = languages == language
        if mask.any():
            rows.append(_row(f"language guess: {language}", correct[mask]))
    if leaked:
        mask = np.array([i in leaked for i in range(len(texts))])
        rows.append(_row("test texts duplicated in train", correct[mask]))
        rows.append(_row("test texts NOT in train (the honest number)", correct[~mask]))
    return rows


def calibration_rows(val_logits, val_labels, test_logits, test_labels) -> dict:
    temperature = fit_temperature(val_logits, val_labels)
    raw, scaled = probabilities(test_logits), probabilities(test_logits, temperature)
    return {
        "temperature": temperature,
        "table": [
            {"probabilities": "raw", "ece": ece(raw, test_labels), "nll": nll(test_logits,
             test_labels), "brier": brier(raw, test_labels)},
            {"probabilities": "temperature-scaled", "ece": ece(scaled, test_labels),
             "nll": nll(test_logits, test_labels, temperature),
             "brier": brier(scaled, test_labels)},
        ],
        "reliability_scaled": reliability_table(scaled, test_labels),
    }


def robustness(predict: Predict, texts: list[str], labels: np.ndarray, sample: int = 1000) -> list:
    rng = np.random.default_rng(0)
    index = rng.permutation(len(texts))[: sample]
    chosen = [texts[i] for i in index]
    original = predict(chosen).argmax(axis=1)
    y = labels[index]
    rows = []
    for name, perturb in PERTURBATIONS.items():
        changed = predict([perturb(t) for t in chosen]).argmax(axis=1)
        rows.append({"perturbation": name, "n": len(chosen),
                     "accuracy_change": float((changed == y).mean() - (original == y).mean()),
                     "flip_rate": float((changed != original).mean())})
    return rows


def evaluate_model(
    name: str,
    test_texts: list[str],
    test_labels: list[int],
    test_logits: np.ndarray,
    val_logits: np.ndarray,
    val_labels: list[int],
    predict: Predict,
    leaked: set[int] | None = None,
) -> dict:
    y = np.asarray(test_labels)
    predictions = test_logits.argmax(axis=1)
    correct = predictions == y
    # Exact duplicates inside the test set are one observation, not several.
    groups = [canonical(t) for t in test_texts]
    calibration = calibration_rows(val_logits, np.asarray(val_labels), test_logits, y)
    scaled = probabilities(test_logits, calibration["temperature"])
    curve = risk_coverage(scaled.max(axis=1), (~correct).astype(float))
    wrong = np.argsort(-scaled.max(axis=1) * ~correct)[:20]
    return {
        "model": name,
        "accuracy": _row("all test data", correct, groups),
        "macro_f1": f1_macro(y, predictions),
        "calibration": calibration,
        "slices": slices(test_texts, y, correct, leaked or set()),
        "selective_prediction": {
            "aurc": curve["aurc"], "oracle_aurc": curve["oracle_aurc"],
            "random_aurc": curve["random_aurc"], "error_at_coverage": risk_at(curve),
        },
        "robustness": robustness(predict, test_texts, y),
        "behaviour": behaviour.run_challenge(predict, behaviour.load_challenge()),
        "confident_errors": [
            {"label": int(y[i]), "confidence": float(scaled[i].max()),
             "text": test_texts[i][:300]}
            for i in wrong if not correct[i]
        ],
        "_correct": correct,
    }


def compare(results: list[dict]) -> list[dict]:
    rows = []
    for index, first in enumerate(results):
        for second in results[index + 1 :]:
            rows.append({"a": first["model"], "b": second["model"],
                         **mcnemar_exact(first["_correct"], second["_correct"])})
    return rows


def build_report(audit: dict, results: list[dict], out_dir, *, provenance: str, config: dict):
    report = {
        "meta": run_metadata(provenance, ["torch", "transformers", "scikit-learn"], config=config),
        "audit": {k: v for k, v in audit.items() if not k.startswith("_")},
        "models": [{k: v for k, v in r.items() if not k.startswith("_")} for r in results],
        "comparisons": compare(results),
    }
    parts = ["# Dutch text classifier evaluation\n", "## Data audit\n",
             markdown_table([{"check": k, "value": v} for k, v in report["audit"].items()])]
    for result in report["models"]:
        parts += [f"\n## {result['model']}\n",
                  f"Macro-F1 {result['macro_f1']:.4f}. Temperature "
                  f"{result['calibration']['temperature']:.3f} (fit on validation).\n",
                  markdown_table([result["accuracy"], *result["slices"]]),
                  "\n### Calibration\n", markdown_table(result["calibration"]["table"]),
                  "\n### Robustness\n", markdown_table(result["robustness"]),
                  "\n### Behavioural tests\n", markdown_table(result["behaviour"]["by_test"])]
    parts += ["\n## Comparisons (exact McNemar)\n", markdown_table(report["comparisons"])]
    write_report(Path(out_dir), report, "\n".join(parts) + "\n")
    return report
