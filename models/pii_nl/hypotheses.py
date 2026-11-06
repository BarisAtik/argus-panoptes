"""Check the pre-registered hypotheses on stored rows from `pii_nl.run score`."""

from __future__ import annotations

import json

import numpy as np
from scipy import stats

from forge.stats import ratio_ci_t

from .evaluate import rate
from .run import OUT, load_rows


def paired_gap(rows: list[dict], group: str, base: str = "dutch") -> dict:
    """Person leak of `group` minus `base`, same templates, cluster t interval over templates."""
    keep = [r for r in rows if r["kind"] == "PERSOON"]
    pairs = []
    for template in sorted({r["template"] for r in keep}):
        one = [r for r in keep if r["template"] == template and r["group"] == group]
        two = [r for r in keep if r["template"] == template and r["group"] == base]
        pairs.append(
            (sum(r["leaked"] for r in one) - sum(r["leaked"] for r in two),
             sum(r["total"] for r in two))
        )
    pair = np.array(pairs, dtype=float)
    k = len(pair)
    gap = pair[:, 0].sum() / pair[:, 1].sum()
    residual = pair[:, 0] - gap * pair[:, 1]
    se = np.sqrt(k / (k - 1) * (residual**2).sum()) / pair[:, 1].sum()
    half = float(stats.t.ppf(0.975, k - 1) * se)
    return {"gap": float(gap), "low": float(gap - half), "high": float(gap + half), "clusters": k}


def main() -> None:
    lg, best, dd = (load_rows("test", n) for n in ("spacy_lg", "rules_lg", "deduce"))
    best_dev = load_rows("dev", "rules_lg")
    groups = ("turkish", "moroccan", "polish", "hindustani")
    registers = ("brief", "beschikking", "chat", "transcript")
    person = [r for r in lg if r["kind"] == "PERSOON"]
    template_ci = rate(person)
    doc_ci = ratio_ci_t(
        np.array([r["leaked"] for r in person], dtype=float),
        np.array([r["total"] for r in person], dtype=float),
        [f"{r['template']}/{r['group']}/{r['repeat']}" for r in person],
    )
    result = {
        "h1_person_leak_lg": rate(lg, kind="PERSOON"),
        "h2_lg_by_register": {
            r: rate(lg, kind="PERSOON", register=r) for r in ("brief", "transcript")
        },
        "h3_spoken_numbers_lg": rate(
            [r for r in lg if r["register"] == "transcript" and r["kind"] in ("TELEFOON", "BSN")]
        ),
        "h4_gap_lg": {g: paired_gap(lg, g) for g in groups},
        "h4_gap_rules_lg": {g: paired_gap(best, g) for g in groups},
        "h5_deduce_vs_lg": {
            r: {
                "deduce": rate(dd, kind="PERSOON", register=r),
                "lg": rate(lg, kind="PERSOON", register=r),
            }
            for r in registers
        },
        "h6_all_kinds": {"lg": rate(lg, kind=None), "rules_lg": rate(best, kind=None)},
        "h6_ordinary_masked": {
            "lg": rate(lg, kind="_outside"),
            "rules_lg": rate(best, kind="_outside"),
        },
        "h7": {"dev": rate(best_dev, kind=None), "test": rate(best, kind=None)},
        "h8": {
            "template_width": template_ci["high"] - template_ci["low"],
            "document_width": doc_ci.high - doc_ci.low,
        },
    }
    (OUT / "hypotheses.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
