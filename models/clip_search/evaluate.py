"""The experiment: same images, same categories, English vs Dutch queries.

Relevance comes from COCO's human object labels, so no caption translation is involved.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from clip_search.backends import Backend
from clip_search.corrupt import CORRUPTIONS
from clip_search.index import embed_paths
from clip_search.labels_nl import COCO_LABELS, FALSE_FRIENDS, TEMPLATES
from forge import retrieval as ret
from forge.report import markdown_table, run_metadata, write_report
from forge.stats import mean_ci, paired_ratio_difference


def build_queries(language: str, categories: list[str], template: bool = True) -> list[str]:
    phrases = [COCO_LABELS[c][0 if language == "en" else 1] for c in categories]
    return [TEMPLATES[language].format(p) for p in phrases] if template else phrases


def metrics(scores: np.ndarray, relevant: np.ndarray) -> dict:
    ap = ret.average_precision(scores, relevant)
    interval = mean_ci(ap, seed=0)
    return {
        "map": interval.estimate, "map_low": interval.low, "map_high": interval.high,
        "p@10": float(ret.precision_at_k(scores, relevant, 10).mean()),
        "recall@100": float(ret.recall_at_k(scores, relevant, 100).mean()),
        "mrr": float(ret.reciprocal_rank(scores, relevant).mean()),
    }


def language_experiment(backend, image_vectors, relevance: dict[str, np.ndarray]) -> dict:
    categories = [c for c in COCO_LABELS if c in relevance and relevance[c].any()]
    relevant = np.stack([relevance[c] for c in categories])
    per_query, rows = {}, []
    for language in ("en", "nl"):
        for template in (True, False):
            text = backend.encode_texts(build_queries(language, categories, template))
            scores = text @ image_vectors.T
            name = f"{language}/{'template' if template else 'bare phrase'}"
            per_query[name] = ret.average_precision(scores, relevant)
            rows.append({"queries": name, **metrics(scores, relevant)})
    gap = paired_ratio_difference(per_query["en/template"], per_query["nl/template"],
                                  np.ones(len(categories)))
    gaps = per_query["en/template"] - per_query["nl/template"]
    order = np.argsort(-gaps)
    worst = [
        {"category": categories[i], "dutch": COCO_LABELS[categories[i]][1],
         "ap_en": float(per_query["en/template"][i]), "ap_nl": float(per_query["nl/template"][i])}
        for i in order[:12]
    ]
    return {
        "chance_map": float(relevant.mean(axis=1).mean()),
        "table": rows,
        "en_minus_nl": gap.as_dict(),
        "largest_gaps": worst,
    }


def false_friend_experiment(backend, image_vectors, relevance) -> list[dict]:
    rows = []
    for word, category in FALSE_FRIENDS.items():
        if category not in relevance or not relevance[category].any():
            continue
        relevant = relevance[category][None, :]
        ap_word = ret.average_precision(backend.encode_texts([word]) @ image_vectors.T, relevant)
        en = COCO_LABELS[category][0]
        ap_en = ret.average_precision(backend.encode_texts([en]) @ image_vectors.T, relevant)
        rows.append({"dutch_word": word, "means": category, "ap_dutch_word": float(ap_word[0]),
                     "ap_english_phrase": float(ap_en[0])})
    return rows


def robustness_experiment(backend, paths, image_vectors, relevance, sample=1000, seed=0) -> list:
    """English queries against degraded images, on a random sample of images."""
    rng = np.random.default_rng(seed)
    index = np.sort(rng.permutation(len(paths))[:sample])
    chosen = [paths[i] for i in index]
    categories = [c for c in COCO_LABELS if c in relevance and relevance[c][index].any()]
    relevant = np.stack([relevance[c][index] for c in categories])
    text = backend.encode_texts(build_queries("en", categories))
    baseline = ret.average_precision(text @ image_vectors[index].T, relevant)
    rows = [{"images": "original", **metrics(text @ image_vectors[index].T, relevant)}]
    for name, corruption in CORRUPTIONS.items():
        vectors = embed_paths(backend, chosen, transform=corruption)
        scores = text @ vectors.T
        drop = paired_ratio_difference(ret.average_precision(scores, relevant), baseline,
                                       np.ones(len(categories)))
        rows.append({"images": name, **metrics(scores, relevant), "change_vs_original":
                     drop.difference, "change_low": drop.low, "change_high": drop.high})
    return rows


def evaluate_backend(
    backend: Backend,
    paths: list[str],
    image_vectors: np.ndarray,
    relevance: dict[str, np.ndarray],
    robustness_sample: int = 1000,
) -> dict:
    return {
        "model": backend.name,
        "language": language_experiment(backend, image_vectors, relevance),
        "false_friends": false_friend_experiment(backend, image_vectors, relevance),
        "robustness": robustness_experiment(backend, paths, image_vectors, relevance,
                                            robustness_sample),
    }


def write_results(results: list[dict], out_dir: str | Path, *, provenance: str, images: int):
    report = {
        "meta": run_metadata(provenance, ["torch", "transformers", "open_clip_torch"],
                             images=images),
        "models": results,
    }
    parts = ["# Dutch vs English image search\n", f"{images} images.\n"]
    for result in results:
        language = result["language"]
        gap = language["en_minus_nl"]
        parts += [
            f"\n## {result['model']}\n",
            f"Chance-level mAP: {language['chance_map']:.4f}. English minus Dutch mAP (templates): "
            f"{gap['difference']:+.4f} [{gap['low']:+.4f}, {gap['high']:+.4f}], "
            f"p={gap['p_value']:.4f}.\n",
            markdown_table(language["table"]),
            "\n### Largest English advantages\n", markdown_table(language["largest_gaps"]),
            "\n### False friends\n", markdown_table(result["false_friends"]),
            "\n### Degraded images (English queries)\n", markdown_table(result["robustness"]),
        ]
    write_report(out_dir, report, "\n".join(parts) + "\n")
    return report
