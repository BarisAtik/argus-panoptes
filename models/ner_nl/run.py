"""Stages of the study. Everything lands in runs/ner_nl, nothing there is committed.

    python -m ner_nl.run audit
    python -m ner_nl.run train --seed 0 [--augment 0.5]
    python -m ner_nl.run evaluate
    python -m ner_nl.run names
    python -m ner_nl.run calibrate
    python -m ner_nl.run review
    python -m ner_nl.run report

`report` writes a curated summary that can be copied to results/ner_nl/.
"""

from __future__ import annotations

import argparse
import csv
import json
import pickle
from pathlib import Path

import numpy as np

from forge.report import markdown_table, run_metadata, write_report
from forge.stats import holm

from . import audit as audit_mod
from . import perturb
from .backends import Gazetteer, SpacyNER
from .data import load_split
from .metrics import entity_ece, paired_f1_difference, recall_by_seen
from .names import NAMES, swap_names
from .spans import ALL_LABELS, SHARED_LABELS, bio_spans, count_by_doc, f1_interval, prf

OUT = Path("runs/ner_nl")
SPACY_MODELS = ("nl_core_news_sm", "nl_core_news_md", "nl_core_news_lg")
SEEDS = (0, 1, 2)
CONDITIONS = {
    "clean": lambda s: list(s),
    "lowercase": perturb.lowercase,
    "transcript": perturb.transcript_style,
}
VECTOR_MODEL = "nl_core_news_lg"


def splits(data_dir=None) -> dict:
    return {name: load_split(name, data_dir) for name in ("train", "dev", "test")}


def word_vectors(data: dict) -> tuple[np.ndarray, dict]:
    """A small table with only the vectors this corpus needs, cached under runs/."""
    cache = OUT / "vectors.pkl"
    if cache.exists():
        return pickle.loads(cache.read_bytes())
    import spacy

    vectors = spacy.load(VECTOR_MODEL, enable=[]).vocab
    words = {t for part in data.values() for s in part for t in s.tokens}
    words |= {w for group in NAMES.values() for part in group.values() for w in part}
    words |= {w.lower() for w in words}
    index, rows = {}, [np.zeros(vectors.vectors.shape[1], dtype=np.float32)]
    for word in sorted(words):
        key = vectors.strings[word]
        if key in vectors.vectors:
            index[word] = len(rows)
            rows.append(vectors.vectors[key])
    table = np.vstack(rows)
    table /= np.maximum(np.linalg.norm(table, axis=1, keepdims=True), 1e-6)
    OUT.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(pickle.dumps((table, index)))
    return table, index


def run_dir(seed: int, augment: float) -> Path:
    return OUT / f"{'own_aug' if augment else 'own'}_s{seed}"


def load_own(path: Path):
    import torch

    from .tagger import BiLSTMCRF, Config, Encoder

    saved = torch.load(path / "model.pt", weights_only=False)
    vectors = torch.zeros_like(saved["state"]["words.weight"])
    model = BiLSTMCRF(vectors, len(saved["chars"]) + 2, Config(**saved["config"]))
    model.load_state_dict(saved["state"])
    return model, Encoder(saved["word_index"], saved["chars"]), saved


class Own:
    def __init__(self, path: Path):
        self.model, self.encoder, self.saved = load_own(path)
        self.name = path.name

    def __call__(self, sentences):
        from .tagger import predict

        return predict(self.model, self.encoder, sentences)


def stage_audit(args) -> None:
    data = splits(args.data_dir)
    result = {
        "splits": {name: audit_mod.describe(part) for name, part in data.items()},
        "dev_vs_train": audit_mod.leakage(data["train"], data["dev"]),
        "test_vs_train": audit_mod.leakage(data["train"], data["test"]),
        "label_conflicts_train": audit_mod.label_conflicts(data["train"]),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "audit.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


def stage_train(args) -> None:
    import torch

    from .tagger import train

    torch.set_num_threads(args.threads)
    data = splits(args.data_dir)
    table, index = word_vectors(data)
    model, encoder, info = train(
        data["train"], data["dev"], table, index, seed=args.seed, augment=args.augment
    )
    path = run_dir(args.seed, args.augment)
    path.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "state": model.state_dict(),
            "chars": encoder.chars,
            "word_index": index,
            "config": info["config"],
        },
        path / "model.pt",
    )
    (path / "info.json").write_text(json.dumps(info, indent=2))


def predictors(data: dict) -> dict:
    found = {"gazetteer": Gazetteer(data["train"])}
    for name in SPACY_MODELS:
        found[name] = SpacyNER(name)
    for path in sorted(OUT.glob("own*_s*")):
        if (path / "model.pt").exists():
            found[path.name] = Own(path)
    return found


def score(sentences, tags, labels) -> dict:
    rows, docs = count_by_doc(sentences, tags, labels)
    return {**prf(rows), "ci": f1_interval(rows, docs).as_dict()}


def stage_evaluate(args) -> None:
    data = splits(args.data_dir)
    results, stored = [], {}
    for name, predict in predictors(data).items():
        for split in ("dev", "test"):
            for condition, change in CONDITIONS.items():
                sentences = change(data[split])
                tags = predict(sentences)
                stored[(name, split, condition)] = tags
                for scope, labels in (("all", ALL_LABELS), ("shared", SHARED_LABELS)):
                    row = score(sentences, tags, labels)
                    row.update(model=name, split=split, condition=condition, scope=scope)
                    results.append(row)
                print(name, split, condition, flush=True)
    (OUT / "predictions.pkl").write_bytes(pickle.dumps(stored))
    (OUT / "evaluate.json").write_text(json.dumps(results, indent=2))


def best_seed(prefix: str) -> str:
    runs = [json.loads((OUT / f"{prefix}_s{s}/info.json").read_text()) for s in SEEDS]
    return f"{prefix}_s{int(np.argmax([r['best_dev_f1'] for r in runs]))}"


def stage_names(args) -> None:
    data = splits(args.data_dir)
    models = {name: SpacyNER(name) for name in SPACY_MODELS}
    for prefix in ("own", "own_aug"):
        name = best_seed(prefix)
        models[name] = Own(OUT / name)
    rows = []
    test = data["test"]
    for repeat in range(args.repeats):
        for group in NAMES:
            sentences, mentions = swap_names(test, group, seed=repeat)
            for name, predict in models.items():
                tags = predict(sentences)
                for m in mentions:
                    predicted = set(bio_spans(tags[m.sentence]))
                    found_types = {s[2] for s in predicted if s[0] < m.end and m.start < s[1]}
                    rows.append(
                        {
                            "model": name,
                            "repeat": repeat,
                            "group": group,
                            "doc": m.doc_id,
                            "name": m.last_name,
                            "mention": f"{m.sentence}:{m.start}",
                            "exact": int((m.start, m.end, "PER") in predicted),
                            "any_overlap": int(bool(found_types)),
                        }
                    )
            print(repeat, group, flush=True)
    with open(OUT / "names.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def _span_records(sentences, confidence):
    conf, correct = [], []
    for s, spans in zip(sentences, confidence):
        gold = set(bio_spans(s.tags))
        for start, end, label, value in spans:
            conf.append(value)
            correct.append((start, end, label) in gold)
    return np.array(conf), np.array(correct, dtype=float)


def stage_calibrate(args) -> None:
    from .tagger import predict_with_confidence, token_nll

    data = splits(args.data_dir)
    results = []
    for prefix in ("own", "own_aug"):
        name = best_seed(prefix)
        own = Own(OUT / name)
        grid = np.exp(np.linspace(np.log(0.5), np.log(4.0), 15))
        losses = [token_nll(own.model, own.encoder, data["dev"], float(t)) for t in grid]
        temperature = float(grid[int(np.argmin(losses))])
        dev = {}
        for t_name, t in (("raw", 1.0), ("scaled", temperature)):
            _, spans = predict_with_confidence(own.model, own.encoder, data["dev"], temperature=t)
            dev[t_name] = _span_records(data["dev"], spans)
        for condition in ("clean", "transcript"):
            sentences = CONDITIONS[condition](data["test"])
            for t_name, t in (("raw", 1.0), ("scaled", temperature)):
                _, spans = predict_with_confidence(own.model, own.encoder, sentences, temperature=t)
                conf, correct = _span_records(sentences, spans)
                row = {
                    "model": name,
                    "condition": condition,
                    "calibration": t_name,
                    "temperature": t,
                    "spans": len(conf),
                    "precision": float(correct.mean()),
                    "mean_confidence": float(conf.mean()),
                    "ece": entity_ece(conf, correct),
                }
                # Keep spans above the dev threshold that reaches 95% precision.
                dev_conf, dev_ok = dev[t_name]
                order = np.argsort(-dev_conf)
                running = np.cumsum(dev_ok[order]) / np.arange(1, len(order) + 1)
                good = np.flatnonzero(running >= 0.95)
                threshold = float(dev_conf[order][good[-1]]) if len(good) else 1.0
                kept = conf >= threshold
                row["threshold_for_dev_95"] = threshold
                row["test_coverage_at_threshold"] = float(kept.mean())
                precision = float(correct[kept].mean()) if kept.any() else None
                row["test_precision_at_threshold"] = precision
                results.append(row)
    (OUT / "calibrate.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


def stage_review(args) -> None:
    """Spans where two unrelated models agree with each other and not with gold."""
    data = splits(args.data_dir)
    stored = pickle.loads((OUT / "predictions.pkl").read_bytes())
    a = stored[(best_seed("own"), "test", "clean")]
    b = stored[("nl_core_news_lg", "test", "clean")]
    items = []
    for i, s in enumerate(data["test"]):
        gold = {x for x in bio_spans(s.tags) if x[2] in SHARED_LABELS}
        both = {x for x in set(bio_spans(a[i])) & set(bio_spans(b[i])) if x[2] in SHARED_LABELS}
        for span in sorted(both - gold):
            start, end, label = span
            over = [g for g in bio_spans(s.tags) if g[0] < end and start < g[1]]
            items.append(
                {
                    "sentence": i,
                    "start": start,
                    "end": end,
                    "predicted": label,
                    "gold_overlap": over,
                    "text": " ".join(s.tokens),
                    "span_text": " ".join(s.tokens[start:end]),
                    "gold_text": [" ".join(s.tokens[g[0]:g[1]]) for g in over],
                }
            )
    rng = np.random.default_rng(args.seed)
    picks = rng.permutation(len(items))[: args.sample]
    (OUT / "review.json").write_text(
        json.dumps(
            {"pool": len(items), "items": [items[i] for i in picks]}, indent=1, ensure_ascii=False
        )
    )
    print(len(items), "candidates")


def _find(rows, **keys):
    return next(r for r in rows if all(r[k] == v for k, v in keys.items()))


def stage_report(args) -> None:
    data = splits(args.data_dir)
    test = data["test"]
    rows = json.loads((OUT / "evaluate.json").read_text())
    stored = pickle.loads((OUT / "predictions.pkl").read_bytes())
    audit = json.loads((OUT / "audit.json").read_text())

    def table(scope, condition="clean", split="test"):
        out = []
        for r in rows:
            if r["scope"] == scope and r["condition"] == condition and r["split"] == split:
                out.append(
                    {
                        "model": r["model"],
                        "F1": r["f1"],
                        "95% CI": f"{r['ci']['low']:.3f} to {r['ci']['high']:.3f}",
                        "P": r["precision"],
                        "R": r["recall"],
                    }
                )
        return out

    best, best_aug = best_seed("own"), best_seed("own_aug")
    comparisons = {}
    pairs = [
        ("lg_vs_sm", "nl_core_news_lg", "nl_core_news_sm", "clean", SHARED_LABELS),
        ("own_vs_lg", best, "nl_core_news_lg", "clean", SHARED_LABELS),
        ("own_vs_gazetteer", best, "gazetteer", "clean", ALL_LABELS),
        ("aug_vs_own_clean", best_aug, best, "clean", ALL_LABELS),
        ("aug_vs_own_transcript", best_aug, best, "transcript", ALL_LABELS),
    ]
    for key, left, right, condition, labels in pairs:
        sentences = CONDITIONS[condition](test)
        a, docs = count_by_doc(sentences, stored[(left, "test", condition)], labels)
        b, _ = count_by_doc(sentences, stored[(right, "test", condition)], labels)
        comparisons[key] = paired_f1_difference(a, b, docs).as_dict()
    # Robustness loss per model, same articles and same gold spans up to dropped punctuation.
    robust = []
    for name in ("nl_core_news_lg", best, best_aug):
        clean = _find(rows, model=name, split="test", condition="clean", scope="shared")
        for condition in ("lowercase", "transcript"):
            changed = _find(rows, model=name, split="test", condition=condition, scope="shared")
            robust.append(
                {
                    "model": name,
                    "condition": condition,
                    "clean F1": clean["f1"],
                    "changed F1": changed["f1"],
                    "loss": clean["f1"] - changed["f1"],
                    "95% CI changed": f"{changed['ci']['low']:.3f} to {changed['ci']['high']:.3f}",
                }
            )
    seen = []
    for name in ("gazetteer", "nl_core_news_lg", best):
        out = recall_by_seen(data["train"], test, stored[(name, "test", "clean")])
        seen.append({"model": name, **out})
    # Article-level against sentence-level intervals for the same score.
    r, docs = count_by_doc(test, stored[(best, "test", "clean")], ALL_LABELS)
    by_doc = f1_interval(r, docs)
    by_sentence = f1_interval(r, [str(i) for i in range(len(r))])
    width = {
        "article_width": by_doc.high - by_doc.low,
        "sentence_width": by_sentence.high - by_sentence.low,
        "n_articles": by_doc.n_clusters,
    }
    seeds = {
        prefix: [
            _find(rows, model=f"{prefix}_s{s}", split="test", condition="clean", scope="all")["f1"]
            for s in SEEDS
        ]
        for prefix in ("own", "own_aug")
    }
    names_summary = []
    names_path = OUT / "names_summary.json"
    if names_path.exists():
        names_summary = json.loads(names_path.read_text())
    calibration = json.loads((OUT / "calibrate.json").read_text())
    p_values = [comparisons[k]["p_value"] for k in comparisons]
    adjusted = holm(p_values)
    for key, value in zip(comparisons, adjusted):
        comparisons[key]["p_holm"] = float(value)

    report = {
        "meta": run_metadata(
            "real", ("torch", "spacy", "nltk", "nl_core_news_lg"), best_seed=best,
            best_seed_aug=best_aug,
        ),
        "audit": audit,
        "tables": {s: table(s) for s in ("all", "shared")},
        "comparisons": comparisons,
        "robustness": robust,
        "recall_by_seen": seen,
        "interval_width": width,
        "seed_f1": seeds,
        "names": names_summary,
        "calibration": calibration,
    }
    compare_rows = [{"comparison": k, **v} for k, v in comparisons.items()]
    md = [
        "# Dutch NER study: results\n",
        f"Corpus: CoNLL-2002 Dutch, test split `ned.testb`, {width['n_articles']} articles. "
        f"Commit {report['meta']['git_sha']}, {report['meta']['created_utc']}. "
        "Intervals resample articles.\n",
        "## All four labels (exact span and label)\n",
        markdown_table(table("all")),
        "## PER, LOC, ORG only (the fair cross-corpus view)\n",
        markdown_table(table("shared")),
        "## Paired differences\n",
        markdown_table(compare_rows),
        "## Robustness\n",
        markdown_table(robust),
        "## Recall by whether the entity string occurred in training\n",
        markdown_table(seen),
        "## Calibration of span confidence\n",
        markdown_table(calibration),
        "## Name swap\n",
        markdown_table(names_summary) if names_summary else "_not run_\n",
    ]
    write_report(OUT / "report", report, "\n".join(md))
    print((OUT / "report/report.md").read_text())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=["audit", "train", "evaluate", "names", "calibrate", "review", "report"],
    )
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--augment", type=float, default=0.0)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--sample", type=int, default=100)
    args = parser.parse_args()
    globals()[f"stage_{args.stage}"](args)


if __name__ == "__main__":
    main()
