"""Black out personal data on a scanned Dutch page. Runs locally, sends nothing out.

    python -m scan_nl.cli page.png -o page_redacted.png

The output is a new image holding only pixels: nothing hidden stays underneath. Ink the reader did
not turn into words is blacked out too, and such pages are flagged for a person (exit code 3). Treat
every output as a first pass: read the measured leak rates in results/scan_nl/ before relying on it.
"""

from __future__ import annotations

import argparse
import json
import sys

import cv2
import numpy as np
from PIL import Image

from . import ocr as ocr_mod
from .audit import redact_words
from .mitigate import unread_regions


def redact_image(image: np.ndarray, system, engine: str = "tesseract_enh", pad: float = 6.0,
                 fail_closed: bool = True):
    """Return the blacked-out page, the number of masked words and regions, and the unread share."""
    words = ocr_mod.ENGINES[engine](image)
    masked, _ = redact_words(words, system)
    scale = image.shape[1] / 2480
    regions, unread = unread_regions(image, words, scale)
    polys = [np.array(words[i].poly, dtype=float) for i in masked]
    polys += regions if fail_closed else []
    out = image.copy()
    for poly in polys:
        centre = poly.mean(axis=0)
        size = np.maximum(np.ptp(poly, axis=0), 1)
        grown = centre + (poly - centre) * (1 + 2 * pad * scale / size)
        cv2.fillPoly(out, [np.round(grown).astype(np.int32)], 0)
    return out, len(masked), len(regions), unread


def load_system(model: str):
    import spacy

    from pii_nl.rules import rule_hits, truecase

    nlp = spacy.load(model)

    def system(text: str) -> list[tuple[int, int]]:
        return [(h.start, h.end) for h in rule_hits(text, nlp, truecase(text))]

    return system


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image")
    parser.add_argument("-o", "--out", required=True)
    parser.add_argument("--model", default="nl_core_news_lg")
    parser.add_argument("--review", type=float, default=0.05, help="flag above this unread ink")
    parser.add_argument("--no-fail-closed", action="store_true")
    args = parser.parse_args()

    image = np.asarray(Image.open(args.image).convert("L"))
    out, words, regions, unread = redact_image(
        image, load_system(args.model), fail_closed=not args.no_fail_closed
    )
    Image.fromarray(out).save(args.out)
    flagged = unread > args.review
    print(json.dumps({"masked_words": words, "unread_regions_masked": regions,
                      "unread_ink_share": round(unread, 3), "needs_review": flagged}))
    sys.exit(3 if flagged else 0)


if __name__ == "__main__":
    main()
