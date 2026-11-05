"""python -m asr_nl.cli run --config asr_nl/configs/laptop.yaml"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from asr_nl.backends import load_backend
from asr_nl.evaluate import evaluate_run
from asr_nl.manifest import audit, read_manifest
from asr_nl.run import prediction_path, transcribe_condition


def run(config: dict) -> None:
    clips = read_manifest(config["manifest"])
    out_dir = Path(config["out_dir"])
    files = []
    for model in config["models"]:
        backend = load_backend(model, config.get("language", "nl"))
        for condition in config["conditions"]:
            print(f"[{model}] {condition}: {len(clips)} clips", flush=True)
            files.append(transcribe_condition(
                backend, clips, condition, out_dir, batch_size=config.get("batch_size", 8)
            ))
    evaluate_run(clips, files, out_dir, provenance="real",
                 min_speakers=config.get("min_speakers", 10))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run_cmd = commands.add_parser("run", help="Transcribe, then evaluate.")
    run_cmd.add_argument("--config", type=Path, required=True)
    eval_cmd = commands.add_parser("evaluate", help="Re-score existing predictions.")
    eval_cmd.add_argument("--config", type=Path, required=True)
    audit_cmd = commands.add_parser("audit", help="Describe a manifest.")
    audit_cmd.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "audit":
        print(json.dumps(audit(read_manifest(args.manifest)), indent=2, ensure_ascii=False))
        return
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    if args.command == "run":
        run(config)
    else:
        out_dir = Path(config["out_dir"])
        files = [prediction_path(out_dir, m, c) for m in config["models"]
                 for c in config["conditions"]]
        evaluate_run(read_manifest(config["manifest"]), [f for f in files if f.exists()], out_dir,
                     provenance="real", min_speakers=config.get("min_speakers", 10))


if __name__ == "__main__":
    main()
