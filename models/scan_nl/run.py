"""Stages. All output lands in runs/scan_nl, nothing there is committed.

    python -m scan_nl.run ocr --split dev --engines tesseract_nld rapidocr
    python -m scan_nl.run score --split dev
    python -m scan_nl.run report --split dev

`ocr` is the slow step and caches every page as JSON, so scoring can be repeated.
"""

from __future__ import annotations

import argparse
import csv
import json
import zlib
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from pathlib import Path

import numpy as np

from forge.report import markdown_table, run_metadata, write_report
from ner_nl.names import NAMES
from pii_nl.evaluate import rate
from pii_nl.generate import generate, load_templates, render
from pii_nl.run import fmt

from . import ocr as ocr_mod
from .audit import audit, error_rate, redact_words, truth_words
from .degrade import CONDITIONS, apply
from .mitigate import conf_masks, digit_masks, repair_digits, unread_regions
from .render import FONTS, render_page

OUT = Path("runs/scan_nl")
REGISTERS = ("brief", "mail", "beschikking", "notitie")
SYSTEM = "rules_lg_tc"
PAD_300 = 6.0  # mask padding in pixels at 300 dpi, scaled with each condition
DIGITS, DIGIT_SHARE, CONF = 5, 0.6, 0.5  # see the card for how these were chosen on dev
DEFENCES = {
    "none": {},
    "repair": {"repair": True},
    "digits": {"digits": True},
    "lowconf": {"conf": True},
    "unread": {"unread": True},
}


def documents(split: str, repeats: int, seed: int = 0) -> list:
    if split == "blind":
        templates = [
            json.loads(line)
            for line in Path(__file__).with_name("templates").joinpath("blind.jsonl").open()
            if line.strip()
        ]
        docs = [render(t, g, r, seed) for t in templates for g in NAMES for r in range(repeats)]
    else:
        keep = {t["id"] for t in load_templates(split) if t["register"] in REGISTERS}
        docs = [d for d in generate(split, repeats, seed) if d.template in keep]
    return docs


def doc_key(doc) -> str:
    return f"{doc.template}_{doc.group}_{doc.repeat}"


def font_for(doc) -> str:
    """Fonts rotate over documents, independent of tradition and fixed for one document."""
    names = sorted(FONTS)
    return names[zlib.crc32(f"{doc.template}/{doc.repeat}/{doc.group}".encode()) % len(names)]


def page_seed(doc, condition: str) -> int:
    return zlib.crc32(f"{doc_key(doc)}/{condition}".encode())


def _ocr_job(job: tuple) -> str:
    split, repeats, index, condition, engine, path = job
    doc = documents(split, repeats)[index]
    page = render_page(doc, font_for(doc))
    image, _ = apply(condition, page.image, page_seed(doc, condition))
    words = ocr_mod.ENGINES[engine](image)
    Path(path).write_text(json.dumps(ocr_mod.to_json(words)), encoding="utf-8")
    return path


def stage_ocr(args) -> None:
    docs = documents(args.split, args.repeats)
    jobs = []
    for index, doc in enumerate(docs):
        for condition in args.conditions:
            for engine in args.engines:
                folder = OUT / "ocr" / args.split / engine / condition
                folder.mkdir(parents=True, exist_ok=True)
                path = folder / f"{doc_key(doc)}.json"
                if not path.exists():
                    jobs.append((args.split, args.repeats, index, condition, engine, str(path)))
    print(len(jobs), "pages to read", flush=True)
    with ProcessPoolExecutor(args.workers) as pool:
        for count, _ in enumerate(pool.map(_ocr_job, jobs, chunksize=4), 1):
            if count % 200 == 0:
                print(count, flush=True)


def build_system(name: str):
    from pii_nl.run import build

    return build(name)


def score_page(doc, condition, engine, system, split, defences=("none",), conf=CONF) -> list[dict]:
    page = render_page(doc, font_for(doc))
    image, matrix = apply(condition, page.image, page_seed(doc, condition))
    if engine == "truth":
        words = truth_words(doc, page, matrix)
        defences = ("none",)
    else:
        path = OUT / "ocr" / split / engine / condition / f"{doc_key(doc)}.json"
        words = ocr_mod.from_json(json.loads(path.read_text(encoding="utf-8")))
    scale = float(np.sqrt(abs(np.linalg.det(matrix[:2, :2]))))
    regions, unread = unread_regions(image, words, scale)
    rows = []
    for name in defences:
        options = DEFENCES[name]
        masked, text = redact_words(words, system, repair_digits if options.get("repair") else None)
        extra = set(masked)
        if options.get("digits"):
            extra |= set(digit_masks(words, DIGITS, DIGIT_SHARE))
        if options.get("conf"):
            extra |= set(conf_masks(words, conf))
        found = audit(
            doc, page, matrix, image.shape[:2], words, sorted(extra), PAD_300 * scale,
            regions if options.get("unread") else (),
        )
        base = {
            "template": doc.template, "register": doc.register, "group": doc.group,
            "repeat": doc.repeat, "font": font_for(doc), "condition": condition, "engine": engine,
            "defence": name, "cer": round(error_rate(doc.text, text), 4),
            "conf": round(float(np.mean([w.conf for w in words])) if words else 0.0, 4),
            "n_words": len(words), "unread": round(unread, 4),
            "cer_glued": round(error_rate(doc.text.replace(" ", ""), text.replace(" ", "")), 4),
        }
        rows += [{**base, **r} for r in found]
    return rows


def _shard(job: tuple) -> list[dict]:
    args, part, parts = job
    docs = documents(args.split, args.repeats)[part::parts]
    run = build_system(args.system)
    system = lru_cache(maxsize=4096)(lambda text: tuple(run(text)))
    rows = []
    for doc in docs:
        for condition in args.conditions:
            for engine in ("truth", *args.engines):
                path = OUT / "ocr" / args.split / engine / condition / f"{doc_key(doc)}.json"
                if engine == "truth" or path.exists():
                    rows += score_page(
                        doc, condition, engine, system, args.split, tuple(args.defences), args.conf
                    )
    return rows


def stage_score(args) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(args.workers) as pool:
        shards = pool.map(_shard, [(args, i, args.workers) for i in range(args.workers)])
        rows = [r for shard in shards for r in shard]
    with open(OUT / f"rows_{args.split}.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def load(split: str, metric: str = "pixel") -> list[dict]:
    with open(OUT / f"rows_{split}.csv", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for r in rows:
        r["leaked"], r["total"] = int(r[metric]), int(r["total"])
        r["cer"], r["conf"] = float(r["cer"]), float(r["conf"])
    return rows


def cer_of(rows: list[dict], column: str = "cer") -> float:
    pages = {(r["template"], r["group"], r["repeat"]): float(r[column]) for r in rows}
    return float(np.mean(list(pages.values()))) if pages else float("nan")


def stage_report(args) -> None:
    rows = [r for r in load(args.split) if r["defence"] == "none"]
    text_rows = [r for r in load(args.split, "text") if r["defence"] == "none"]
    table = []
    for engine in ("truth", *args.engines):
        for condition in args.conditions:
            chosen = [r for r in rows if r["engine"] == engine and r["condition"] == condition]
            texts = [r for r in text_rows if r["engine"] == engine and r["condition"] == condition]
            if not chosen:
                continue
            table.append(
                {
                    "engine": engine, "condition": condition, "CER": f"{cer_of(chosen):.3f}",
                    "CER no spaces": f"{cer_of(chosen, 'cer_glued'):.3f}",
                    "pixel leak": fmt(rate(chosen, kind=None)),
                    "text-audit leak": fmt(rate(texts, kind=None)),
                    "ordinary words masked": fmt(rate(chosen, kind="_outside")),
                }
            )
    report = {
        "meta": run_metadata(
            "real", ("spacy", "nl_core_news_lg", "rapidocr_onnxruntime", "opencv-python-headless"),
            split=args.split, system=SYSTEM,
        ),
        "table": table,
    }
    md = [
        f"# Scan redaction audit: {args.split}\n",
        f"Commit {report['meta']['git_sha']}, {report['meta']['created_utc']}. Share of values "
        "with a word left visible; 95% cluster t intervals over templates. Synthetic pages.\n",
        markdown_table(table),
    ]
    write_report(OUT / f"report_{args.split}", report, "\n".join(md))
    print("\n".join(md))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["ocr", "score", "report"])
    parser.add_argument("--split", default="dev", choices=["dev", "blind"])
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--engines", nargs="+", default=list(ocr_mod.ENGINES))
    parser.add_argument("--conditions", nargs="+", default=list(CONDITIONS))
    parser.add_argument("--system", default=SYSTEM)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--defences", nargs="+", default=list(DEFENCES))
    parser.add_argument("--conf", type=float, default=CONF)
    args = parser.parse_args()
    {"ocr": stage_ocr, "score": stage_score, "report": stage_report}[args.stage](args)


if __name__ == "__main__":
    main()
