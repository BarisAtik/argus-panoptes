"""Turn raw predictions into a report: overall, per condition, per group, pairwise, failures."""

from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

import numpy as np
from scipy import stats as sps

from asr_nl.alignment import char_errors, score
from asr_nl.manifest import Clip, audit
from asr_nl.normalize import normalize_dutch
from asr_nl.run import read_predictions
from forge.calibration import risk_at, risk_coverage
from forge.report import markdown_table, run_metadata, write_report
from forge.stats import holm, paired_ratio_difference, ratio_ci, wilson_interval

SLICE_FIELDS = ("accent", "gender", "age")


def score_rows(clips: dict[str, Clip], predictions: list[dict]) -> list[dict]:
    rows = []
    for pred in predictions:
        clip = clips.get(pred["id"])
        if clip is None:
            continue
        ref, hyp = normalize_dutch(clip.text), normalize_dutch(pred["hypothesis"])
        counts = score(ref, hyp)
        blind = score(normalize_dutch(clip.text, diacritics=False),
                      normalize_dutch(pred["hypothesis"], diacritics=False))
        raw = score(clip.text.lower(), pred["hypothesis"].lower())
        chars, n_chars = char_errors(ref, hyp)
        rows.append({
            "id": clip.id, "speaker": clip.speaker, "clip": clip,
            "errors": counts.errors, "words": counts.reference_words,
            "subs": counts.substitutions, "dels": counts.deletions, "ins": counts.insertions,
            "errors_no_diacritics": blind.errors,
            "errors_raw": raw.errors, "words_raw": raw.reference_words,
            "compound": counts.compound_cost,
            "chars": chars, "n_chars": n_chars,
            "pairs": counts.pairs,
            "avg_logprob": pred.get("avg_logprob"),
            "seconds": pred.get("seconds"), "audio_seconds": pred.get("audio_seconds"),
            "hypothesis": pred["hypothesis"], "reference": clip.text,
        })
    return rows


def _column(rows, name):
    return np.array([r[name] for r in rows], dtype=float)


def summarize(rows: list[dict], seed: int = 0) -> dict:
    speakers = [r["speaker"] for r in rows]
    words = _column(rows, "words")
    wer = ratio_ci(_column(rows, "errors"), words, speakers, seed=seed)
    cer = ratio_ci(_column(rows, "chars"), _column(rows, "n_chars"), speakers, seed=seed)
    total = words.sum()
    audio = sum(r["audio_seconds"] or 0 for r in rows)
    compute = sum(r["seconds"] or 0 for r in rows)
    return {
        "clips": len(rows),
        "speakers": wer.n_clusters,
        "wer": wer.estimate, "wer_low": wer.low, "wer_high": wer.high,
        "cer": cer.estimate,
        "substitution_rate": _column(rows, "subs").sum() / total,
        "deletion_rate": _column(rows, "dels").sum() / total,
        "insertion_rate": _column(rows, "ins").sum() / total,
        # How much the headline depends on scoring decisions:
        "wer_unnormalized": _column(rows, "errors_raw").sum() / _column(rows, "words_raw").sum(),
        "wer_no_diacritics": _column(rows, "errors_no_diacritics").sum() / total,
        "wer_ignoring_compound_spacing":
            max(0.0, _column(rows, "errors").sum() - _column(rows, "compound").sum()) / total,
        "realtime_factor": (compute / audio) if audio else None,
    }


def slice_rows(rows: list[dict], field: str, min_speakers: int, seed: int = 0) -> list[dict]:
    """Groups with too few speakers are shown as such, not given a false-precision number."""
    groups = defaultdict(list)
    for row in rows:
        groups[getattr(row["clip"], field) or "(missing)"].append(row)
    table = []
    for value, group in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        n_speakers = len({r["speaker"] for r in group})
        row = {"field": field, "group": value, "clips": len(group), "speakers": n_speakers}
        if n_speakers >= min_speakers:
            interval = ratio_ci(_column(group, "errors"), _column(group, "words"),
                                [r["speaker"] for r in group], seed=seed)
            row.update(wer=interval.estimate, wer_low=interval.low, wer_high=interval.high)
        else:
            row.update(wer=None, wer_low=None, wer_high=None, note="too few speakers")
        table.append(row)
    return table


def pairwise(by_model: dict[str, list[dict]], condition: str, seed: int = 0) -> list[dict]:
    """All model pairs on their shared clips, Holm-corrected within the condition."""
    table = []
    for model_a, model_b in combinations(sorted(by_model), 2):
        rows_a = {r["id"]: r for r in by_model[model_a]}
        rows_b = {r["id"]: r for r in by_model[model_b]}
        shared = sorted(rows_a.keys() & rows_b.keys())
        if not shared:
            continue
        result = paired_ratio_difference(
            [rows_a[i]["errors"] for i in shared], [rows_b[i]["errors"] for i in shared],
            [rows_a[i]["words"] for i in shared], [rows_a[i]["speaker"] for i in shared],
            seed=seed,
        )
        table.append({
            "condition": condition, "a": model_a, "b": model_b, "clips": len(shared),
            "wer_a": result.a, "wer_b": result.b, "difference": result.difference,
            "low": result.low, "high": result.high, "p": result.p_value,
        })
    for row, adjusted in zip(table, holm([r["p"] for r in table]) if table else []):
        row["p_holm"] = adjusted
    return table


def hallucination(predictions: list[dict]) -> dict:
    """On speech-free audio the right output is nothing."""
    texts = [normalize_dutch(p["hypothesis"]) for p in predictions]
    outputs = sum(1 for t in texts if t)
    low, high = wilson_interval(outputs, len(texts))
    return {
        "clips": len(texts),
        "clips_with_output": outputs,
        "rate": outputs / max(1, len(texts)),
        "rate_low": low, "rate_high": high,
        "mean_words": float(np.mean([len(t.split()) for t in texts])) if texts else 0.0,
        "most_common": Counter(t for t in texts if t).most_common(5),
    }


def confidence_analysis(rows: list[dict]) -> dict | None:
    """Can the model's own score flag bad transcripts, so a human reviews only those?"""
    usable = [r for r in rows if r["avg_logprob"] is not None and r["words"] > 0]
    if len(usable) < 10:
        return None
    confidence = _column(usable, "avg_logprob")
    clip_wer = _column(usable, "errors") / _column(usable, "words")
    if np.ptp(confidence) == 0 or np.ptp(clip_wer) == 0:
        return {"clips": len(usable), "note": "no variation in score or error"}
    rho = sps.spearmanr(confidence, clip_wer).statistic
    curve = risk_coverage(confidence, clip_wer)
    return {
        "clips": len(usable), "spearman_logprob_vs_clip_wer": float(rho),
        "aurc": curve["aurc"], "oracle_aurc": curve["oracle_aurc"],
        "random_aurc": curve["random_aurc"], "mean_clip_wer_at_coverage": risk_at(curve),
    }


def top_failures(rows: list[dict], k: int = 25) -> dict:
    pairs: Counter = Counter()
    for row in rows:
        pairs.update(row["pairs"])
    ranked = sorted((r for r in rows if r["words"]), key=lambda r: -r["errors"] / r["words"])
    return {
        "confusions": [
            {"reference": a, "hypothesis": b, "count": n} for (a, b), n in pairs.most_common(k)
        ],
        "worst_clips": [
            {"id": r["id"], "reference": r["reference"], "hypothesis": r["hypothesis"],
             "clip_wer": r["errors"] / r["words"]}
            for r in ranked[:10]
        ],
    }


def evaluate_run(
    clips: list[Clip],
    prediction_files: list[Path],
    out_dir: str | Path,
    *,
    provenance: str,
    min_speakers: int = 10,
) -> dict:
    lookup = {clip.id: clip for clip in clips}
    predictions: dict[str, dict[str, list[dict]]] = defaultdict(dict)
    for path in prediction_files:
        rows = read_predictions(path)
        if rows:
            predictions[rows[0]["model"]][rows[0]["condition"]] = rows

    summary, slices, pairs, halluc, confidence, failures = [], [], [], [], [], {}
    conditions = sorted({c for per_model in predictions.values() for c in per_model})
    for condition in conditions:
        scored = {}
        for model, per_condition in sorted(predictions.items()):
            if condition not in per_condition:
                continue
            if condition == "noise_only":
                halluc.append({"model": model, **hallucination(per_condition[condition])})
                continue
            rows = [r for r in score_rows(lookup, per_condition[condition]) if r["words"]]
            if not rows:
                continue
            scored[model] = rows
            summary.append({"model": model, "condition": condition, **summarize(rows)})
            if condition == "clean":
                for field in SLICE_FIELDS:
                    slices += [{"model": model, **r}
                               for r in slice_rows(rows, field, min_speakers)]
                analysis = confidence_analysis(rows)
                if analysis:
                    confidence.append({"model": model, **analysis})
                failures[model] = top_failures(rows)
        pairs += pairwise(scored, condition)

    report = {
        "meta": run_metadata(provenance, ["torch", "transformers", "faster-whisper"],
                             min_speakers=min_speakers),
        "sample_audit": audit(clips),
        "summary": summary, "slices": slices, "pairwise": pairs,
        "hallucination": halluc, "confidence": confidence, "failures": failures,
    }
    write_report(out_dir, report, render_markdown(report))
    return report


def render_markdown(report: dict) -> str:
    audit_info = report["sample_audit"]
    main_cols = ["model", "condition", "clips", "speakers", "wer", "wer_low", "wer_high", "cer",
                 "wer_unnormalized", "wer_no_diacritics", "wer_ignoring_compound_spacing",
                 "realtime_factor"]
    parts = [
        "# Dutch ASR evaluation\n",
        f"{audit_info['clips']} clips from {audit_info['speakers']} speakers. "
        "Intervals are 95% speaker-level bootstrap.\n",
    ]
    parts += [f"- ⚠️ {w}" for w in audit_info["warnings"]]
    parts += ["\n## Results by model and condition\n", markdown_table(report["summary"], main_cols)]
    parts += ["\n## Groups (clean audio)\n",
              markdown_table(report["slices"], ["model", "field", "group", "clips", "speakers",
                                                "wer", "wer_low", "wer_high", "note"])]
    parts += ["\n## Pairwise differences (a − b, negative = a is better)\n",
              markdown_table(report["pairwise"])]
    parts += ["\n## Hallucination on speech-free audio\n",
              markdown_table([{k: v for k, v in r.items() if k != "most_common"}
                              for r in report["hallucination"]])]
    if report["confidence"]:
        rows = [{k: v for k, v in r.items() if k != "mean_clip_wer_at_coverage"}
                for r in report["confidence"]]
        parts += ["\n## Is the model's confidence useful?\n", markdown_table(rows)]
    for model, info in report["failures"].items():
        parts += [f"\n## Top confusions: {model}\n", markdown_table(info["confusions"][:15])]
    return "\n".join(parts) + "\n"
