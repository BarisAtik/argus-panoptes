"""Black out personal data on a scanned Dutch page. Runs locally, sends nothing out.

    python -m scan_nl.cli page.png -o page_redacted.png --review 0.80

The output is a new image holding only pixels: nothing hidden stays underneath. Pages the reader
is unsure about are flagged for a person. Treat every output as a first pass: read the measured
leak rates in results/scan_nl/ before relying on it.
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
from .mitigate import conf_masks, digit_masks, repair_digits


def redact_image(image: np.ndarray, system, engine: str = "tesseract_enh", pad: float = 6.0,
                 conf: float = 0.5, digits: int = 5, share: float = 0.6):
    """Return the blacked-out grey array, the masked words and the mean reading confidence."""
    words = ocr_mod.ENGINES[engine](image)
    masked, _ = redact_words(words, system, repair_digits)
    chosen = set(masked) | set(digit_masks(words, digits, share)) | set(conf_masks(words, conf))
    chosen = sorted(chosen)
    out = image.copy()
    for index in chosen:
        poly = np.array(words[index].poly, dtype=float)
        centre = poly.mean(axis=0)
        grown = centre + (poly - centre) * (1 + 2 * pad / np.maximum(np.ptp(poly, axis=0), 1))
        cv2.fillPoly(out, [np.round(grown).astype(np.int32)], 0)
    confidence = float(np.mean([w.conf for w in words])) if words else 0.0
    return out, [words[i] for i in chosen], confidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image")
    parser.add_argument("-o", "--out", required=True)
    parser.add_argument("--model", default="nl_core_news_lg")
    parser.add_argument("--review", type=float, default=0.80, help="flag pages under this conf")
    args = parser.parse_args()

    import spacy

    from pii_nl.rules import rule_hits, truecase

    nlp = spacy.load(args.model)

    def system(text: str) -> list[tuple[int, int]]:
        return [(h.start, h.end) for h in rule_hits(text, nlp, truecase(text))]

    image = np.asarray(Image.open(args.image).convert("L"))
    out, masked, confidence = redact_image(image, system)
    Image.fromarray(out).save(args.out)
    flagged = confidence < args.review
    print(json.dumps({"masked_words": len(masked), "mean_confidence": round(confidence, 3),
                      "needs_review": flagged}))
    sys.exit(3 if flagged else 0)


if __name__ == "__main__":
    main()
