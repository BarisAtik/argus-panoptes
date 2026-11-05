"""Index COCO val2017 and run the English-vs-Dutch experiment.

    python -m clip_search.coco --out runs/coco
    python -m clip_search.cli --coco runs/coco --out runs/clip \
        --model hf:openai/clip-vit-base-patch32 \
        --model openclip:xlm-roberta-base-ViT-B-32:laion5b_s13b_b90k
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np

from clip_search.backends import load_backend
from clip_search.coco import load_annotations
from clip_search.evaluate import evaluate_backend, write_results
from clip_search.index import ImageIndex, embed_paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--coco", type=Path, default=Path("runs/coco"))
    parser.add_argument("--out", type=Path, default=Path("runs/clip"))
    parser.add_argument("--model", action="append", required=True)
    parser.add_argument("--max-images", type=int)
    parser.add_argument("--robustness-sample", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    names, relevance, _ = load_annotations(args.coco / "annotations" / "instances_val2017.json")
    keep = np.arange(len(names))
    if args.max_images and args.max_images < len(names):
        rng = np.random.default_rng(args.seed)
        keep = np.sort(rng.permutation(len(names))[: args.max_images])
    paths = [str(args.coco / "val2017" / names[i]) for i in keep]
    relevance = {name: values[keep] for name, values in relevance.items()}

    results = []
    for spec in args.model:
        backend = load_backend(spec)
        folder = args.out / "index" / re.sub(r"[^A-Za-z0-9._-]+", "_", spec)
        if (folder / "embeddings.npy").exists():
            vectors = ImageIndex.load(folder).embeddings
        else:
            vectors = embed_paths(backend, paths, progress=True)
            ImageIndex(vectors, [names[i] for i in keep]).save(folder)
        results.append(evaluate_backend(backend, paths, vectors, relevance,
                                        args.robustness_sample))
    write_results(results, args.out, provenance="real", images=len(paths))
    print(f"Report: {args.out / 'report.md'}")


if __name__ == "__main__":
    main()
