"""Run the full experiment: audit, baseline, fine-tune, evaluate.

    python -m text_nl.cli --out runs/text                # full run, GPU recommended
    python -m text_nl.cli --out runs/quick --max-train 4000 --epochs 2   # quick laptop GPU run
    python -m text_nl.cli --out runs/baseline --baseline-only            # CPU, minutes
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from text_nl import baseline
from text_nl.audit import audit_splits, group_split
from text_nl.data import Split, load_dbrd, load_dbrd_archive, load_jsonl
from text_nl.evaluate import build_report, evaluate_model


def run_experiment(
    train: Split,
    test: Split,
    out: Path,
    *,
    provenance: str,
    model_config=None,
    seed: int = 0,
    max_train: int | None = None,
    val_fraction: float = 0.15,
    hf_model=None,
    hf_tokenizer=None,
    audit_kwargs: dict | None = None,
) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    audit = audit_splits(train, test, **(audit_kwargs or {}))
    groups = audit.pop("_groups")
    leaked = set(audit.pop("_test_leaked"))
    train_groups = groups[: len(train)]
    fit_index, val_index = group_split(train.labels, train_groups, val_fraction, seed)
    if max_train and len(fit_index) > max_train:
        rng = np.random.default_rng(seed)
        fit_index = sorted(rng.choice(fit_index, max_train, replace=False).tolist())
    fit_split, val_split = train.subset(fit_index), train.subset(val_index)

    results = []
    model = baseline.make_baseline(seed).fit(fit_split.texts, fit_split.labels)
    predict_baseline = lambda texts: baseline.logits(model, texts)  # noqa: E731
    results.append(evaluate_model(
        "tfidf-logreg", test.texts, test.labels, predict_baseline(test.texts),
        predict_baseline(val_split.texts), val_split.labels, predict_baseline, leaked,
    ))

    oof = baseline.out_of_fold_probabilities(
        fit_split.texts, fit_split.labels, train_groups[fit_index], seed=seed
    )
    suspects = baseline.suspicious_labels(fit_split.texts, fit_split.labels, oof)
    (out / "suspicious_labels.json").write_text(
        json.dumps(suspects, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    if model_config is not None:
        from text_nl.train import fit, predict_logits

        hf, tokenizer, _ = fit(fit_split, val_split, model_config, out / "checkpoint",
                               model=hf_model, tokenizer=hf_tokenizer)
        device = next(hf.parameters()).device
        predict_hf = lambda texts: predict_logits(hf, tokenizer, texts, model_config, device)  # noqa: E731
        test_logits = predict_hf(test.texts)
        results.append(evaluate_model(
            model_config.model, test.texts, test.labels, test_logits,
            predict_hf(val_split.texts), val_split.labels, predict_hf, leaked,
        ))
    config = {"seed": seed, "max_train": max_train, "fit": len(fit_split), "val": len(val_split)}
    return build_report(audit, results, out, provenance=provenance, config=config)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=Path("runs/text"))
    parser.add_argument("--train-jsonl", type=Path, help="Use your own data instead of DBRD.")
    parser.add_argument("--test-jsonl", type=Path)
    parser.add_argument("--dbrd-folder", type=Path, help="Unpacked DBRD release, if not via HF.")
    parser.add_argument("--model", default="pdelobelle/robbert-v2-dutch-base")
    parser.add_argument("--truncation", default="head_tail", choices=["head", "head_tail"])
    parser.add_argument("--max-train", type=int)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--baseline-only", action="store_true")
    args = parser.parse_args()

    if args.train_jsonl:
        train, test = load_jsonl(args.train_jsonl), load_jsonl(args.test_jsonl)
    else:
        data = load_dbrd_archive(args.dbrd_folder) if args.dbrd_folder else load_dbrd()
        train, test = data["train"], data["test"]
    config = None
    if not args.baseline_only:
        from text_nl.train import TrainConfig

        config = TrainConfig(model=args.model, truncation=args.truncation, epochs=args.epochs,
                             batch_size=args.batch_size, seed=args.seed)
    run_experiment(train, test, args.out, provenance="real", model_config=config, seed=args.seed,
                   max_train=args.max_train)
    print(f"Report: {args.out / 'report.md'}")


if __name__ == "__main__":
    main()
