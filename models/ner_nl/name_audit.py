"""Is the name gap a property of a tradition, or of twenty hand-picked names?

    python -m ner_nl.name_audit run --repeats 5
    python -m ner_nl.name_audit report

Two checks on the swap test. Per name: how recall is spread inside a list, what predicts it, and
whether the gap survives when names, not only articles, are resampled. Independent lists: the same
test with the name tables shipped in the Faker package, which nobody here chose.
"""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import random
import unicodedata
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy import stats

from forge.report import markdown_table, run_metadata, write_report

from .backends import SpacyNER
from .names import NAMES, swap_names
from .run import OUT, splits
from .spans import bio_spans

FAKER = {"faker_dutch": "nl_NL", "faker_turkish": "tr_TR", "faker_polish": "pl_PL"}
MODEL = "nl_core_news_lg"
LIST_SIZE = 200


def fold(name: str) -> str:
    """Strip accents, the way many Dutch systems store a Polish or Turkish name."""
    swapped = name.replace("ł", "l").replace("Ł", "L").replace("ı", "i")
    return "".join(
        c for c in unicodedata.normalize("NFKD", swapped) if not unicodedata.combining(c)
    )


def faker_pool(locale: str, size: int = LIST_SIZE, seed: int = 0) -> dict[str, list[str]]:
    """A fixed sample of single-word names from a locale's tables, without their weights."""
    provider = importlib.import_module(f"faker.providers.person.{locale}").Provider
    rng = random.Random(f"{locale}/{seed}")

    def pick(names) -> list[str]:
        unique = sorted({n for n in names if n.isalpha() and n[0].isupper() and len(n) > 1})
        return rng.sample(unique, min(size, len(unique)))

    # Polish tables split surnames by gender and leave `last_names` as a placeholder.
    last = getattr(provider, "last_names_male", None) or provider.last_names
    return {"first": pick(provider.first_names), "last": pick(last)}


def pools() -> dict[str, dict[str, list[str]]]:
    out = dict(NAMES)
    for label, locale in FAKER.items():
        out[label] = faker_pool(locale)
    polish = out["faker_polish"]
    out["faker_polish_folded"] = {k: [fold(n) for n in v] for k, v in polish.items()}
    turkish = out["faker_turkish"]
    out["faker_turkish_folded"] = {k: [fold(n) for n in v] for k, v in turkish.items()}
    return out


def stage_run(args) -> None:
    test = splits(args.data_dir)["test"]
    model = SpacyNER(MODEL)
    rows = []
    for repeat in range(args.repeats):
        for group, pool in pools().items():
            sentences, mentions = swap_names(test, group, seed=repeat, pool=pool)
            tags = model(sentences)
            for m in mentions:
                predicted = set(bio_spans(tags[m.sentence]))
                rows.append(
                    {
                        "repeat": repeat,
                        "group": group,
                        "doc": m.doc_id,
                        "name": m.last_name,
                        "exact": int((m.start, m.end, "PER") in predicted),
                    }
                )
            print(repeat, group, flush=True)
    with open(OUT / "name_audit.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def recall_table(rows: list[dict], group: str) -> dict[str, list[int]]:
    """name -> [hits, mentions]"""
    table: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in rows:
        if r["group"] == group:
            table[r["name"]][0] += int(r["exact"])
            table[r["name"]][1] += 1
    return table


def spread(table: dict[str, list[int]]) -> dict:
    values = sorted(h / n for h, n in table.values())
    return {
        "names": len(values),
        "recall": sum(h for h, _ in table.values()) / sum(n for _, n in table.values()),
        "worst": values[0],
        "p25": float(np.quantile(values, 0.25)),
        "median": float(np.median(values)),
        "p75": float(np.quantile(values, 0.75)),
        "best": values[-1],
    }


def drop_worst(table: dict[str, list[int]], k: int = 3) -> float:
    kept = sorted(table.values(), key=lambda v: v[0] / v[1])[k:]
    return sum(h for h, _ in kept) / sum(n for _, n in kept)


def two_way_gap(
    rows: list[dict], group: str, reference: str, n_boot: int = 2000, seed: int = 0
) -> dict:
    """Gap in recall, with both lists' names and the articles resampled.

    Pigeonhole two-way bootstrap: each draw reweights names and articles independently. Keeps the
    answer honest about a question that article resampling alone can't see, namely what another
    equally valid list of names would have given.
    """
    rng = np.random.default_rng(seed)
    docs = sorted({r["doc"] for r in rows})
    doc_at = {d: i for i, d in enumerate(docs)}
    cells = {}
    for label in (group, reference):
        names = sorted({r["name"] for r in rows if r["group"] == label})
        name_at = {n: i for i, n in enumerate(names)}
        hits = np.zeros((len(names), len(docs)))
        total = np.zeros((len(names), len(docs)))
        for r in rows:
            if r["group"] == label:
                hits[name_at[r["name"]], doc_at[r["doc"]]] += int(r["exact"])
                total[name_at[r["name"]], doc_at[r["doc"]]] += 1
        cells[label] = (hits, total)

    def recall(label, doc_w, name_w):
        hits, total = cells[label]
        return (name_w @ hits @ doc_w) / (name_w @ total @ doc_w)

    point = recall(group, np.ones(len(docs)), np.ones(cells[group][0].shape[0])) - recall(
        reference, np.ones(len(docs)), np.ones(cells[reference][0].shape[0])
    )
    draws = []
    for _ in range(n_boot):
        doc_w = rng.multinomial(len(docs), np.ones(len(docs)) / len(docs)).astype(float)
        one = rng.multinomial(cells[group][0].shape[0], np.ones(cells[group][0].shape[0])
                              / cells[group][0].shape[0]).astype(float)
        two = rng.multinomial(cells[reference][0].shape[0], np.ones(cells[reference][0].shape[0])
                              / cells[reference][0].shape[0]).astype(float)
        draws.append(recall(group, doc_w, one) - recall(reference, doc_w, two))
    low, high = np.nanquantile(draws, [0.025, 0.975])
    return {"gap": float(point), "low": float(low), "high": float(high)}


def stage_report(args) -> None:
    from wordfreq import zipf_frequency

    with open(OUT / "name_audit.csv", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    groups = list(pools())
    tables = {g: recall_table(rows, g) for g in groups}
    spreads = [{"list": g, **spread(tables[g])} for g in groups]

    hand = [g for g in groups if g in NAMES]
    freq, recall = [], []
    for group in hand:
        for name, (hits, total) in tables[group].items():
            freq.append(zipf_frequency(name.lower(), "nl"))
            recall.append(hits / total)
    rho = stats.spearmanr(freq, recall)

    gaps, leave_out = [], []
    pairs = [(g, "dutch") for g in hand if g != "dutch"]
    pairs += [
        (g, "faker_dutch") for g in groups if g.startswith("faker_") and g != "faker_dutch"
    ]
    for group, reference in pairs:
        gaps.append({"list": group, "reference": reference,
                     **two_way_gap(rows, group, reference)})
    reference = spread(tables["dutch"])["recall"]
    for group in hand:
        if group != "dutch":
            leave_out.append(
                {
                    "list": group,
                    "gap": spread(tables[group])["recall"] - reference,
                    "gap_without_worst_3": drop_worst(tables[group]) - reference,
                }
            )
    worst = {
        g: sorted(
            ({"name": n, "recall": h / t} for n, (h, t) in tables[g].items()),
            key=lambda x: x["recall"],
        )[:5]
        for g in hand
    }
    report = {
        "meta": run_metadata("real", ("spacy", MODEL, "faker", "wordfreq"), model=MODEL),
        "spread": spreads,
        "two_way_gaps": gaps,
        "leave_out": leave_out,
        "zipf_vs_recall": {"spearman": float(rho.statistic), "p": float(rho.pvalue),
                           "names": len(freq)},
        "worst_names": worst,
    }
    md = [
        "# Name gap: per name and with independent lists\n",
        f"Model {MODEL}, exact PER recall on swapped names, CoNLL-2002 Dutch test. Commit "
        f"{report['meta']['git_sha']}, {report['meta']['created_utc']}.\n",
        "## Spread inside each list\n", markdown_table(spreads),
        "## Gaps with names and articles resampled\n", markdown_table(gaps),
        "## Leave out the three worst names\n", markdown_table(leave_out),
        f"Spearman of Dutch word frequency and recall, hand lists: {rho.statistic:.2f} "
        f"(p {rho.pvalue:.3g}, {len(freq)} names).\n",
    ]
    write_report(OUT / "report_name_audit", report, "\n".join(md))
    print("\n".join(md))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["run", "report"])
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args()
    {"run": stage_run, "report": stage_report}[args.stage](args)


if __name__ == "__main__":
    main()
