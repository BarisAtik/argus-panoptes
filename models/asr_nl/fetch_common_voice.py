"""Download Common Voice Dutch from Mozilla Data Collective (needs your own MDC_API_KEY).

Common Voice moved off Hugging Face in October 2025. Accept the dataset terms on its page, then:

    export MDC_API_KEY=...            # never commit this
    python -m asr_nl.fetch_common_voice --dataset <id-or-slug-from-the-page> --out runs/cv_nl
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from asr_nl.manifest import from_common_voice_tsv, sample_clips, write_manifest

# Scripted Speech 23.0 - Dutch, id from the dataset's public URL. Check for newer releases.
DEFAULT_DATASET = "cmflnuzw612cjai01qcld1gt5"


def find_split(root: Path, split: str) -> Path:
    matches = sorted(root.rglob(f"{split}.tsv"))
    if not matches:
        raise FileNotFoundError(f"no {split}.tsv under {root}; list the archive and adjust")
    return matches[0]


def build_manifest(root: Path, out: Path, split: str, n: int, cap: int, seed: int) -> Path:
    tsv = find_split(root, split)
    candidates = sorted(tsv.parent.rglob("clips")) + sorted(root.rglob("clips"))
    clips_dir = next((c for c in candidates if c.is_dir()), None)
    if clips_dir is None:
        raise FileNotFoundError(f"no clips/ directory under {root}")
    clips = from_common_voice_tsv(tsv, clips_dir)
    sample = sample_clips(clips, n, per_speaker_cap=cap, seed=seed)
    manifest = out / f"manifest_{split}_{n}.jsonl"
    if len(sample) < n:
        print(f"Only {len(sample)} clips available for n={n} at this per-speaker cap.")
    write_manifest(sample, manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--out", type=Path, default=Path("runs/cv_nl"))
    parser.add_argument("--split", default="test")
    parser.add_argument("--n", type=int, default=1000)
    parser.add_argument("--per-speaker-cap", type=int, default=5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--skip-download", action="store_true",
                        help="Only rebuild the manifest from an already extracted archive.")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if not args.skip_download:
        if not os.environ.get("MDC_API_KEY"):
            raise SystemExit("Set MDC_API_KEY first (see the docstring).")
        import shutil

        from datacollective import download_dataset

        archive = Path(download_dataset(args.dataset, download_directory=str(args.out)))
        if archive.is_file():
            shutil.unpack_archive(archive, args.out)
    manifest = build_manifest(args.out, args.out, args.split, args.n, args.per_speaker_cap,
                              args.seed)
    print(f"Manifest: {manifest}")


if __name__ == "__main__":
    main()
