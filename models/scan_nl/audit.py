"""Turn OCR words into masks and audit them against the true ink.

A word of a value counts as hidden when masks cover at least `HIDDEN` of its true box in the damaged
image. A value leaks if any of its words stays visible, the same rule as `pii_nl`, now in pixels.
`text_leaked` is what a text-only audit would report for the same masks: a true word still
readable, verbatim, in the OCR text outside any mask. The difference is the blind spot of such
audits.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import cv2
import numpy as np

from pii_nl.evaluate import WORD
from pii_nl.generate import Document

from .degrade import corners
from .ocr import OcrWord, assemble
from .render import Page, gold_boxes

HIDDEN = 0.90
# Name particles also occur as ordinary words, so finding one in the text proves nothing.
PARTICLES = frozenset("van de der den ter ten te het".split())
RASTER = 0.25  # audit raster, in share of damaged-image pixels per axis
Ranges = Callable[[str], Sequence[tuple[int, int]]]


def edit_distance(a: Sequence, b: Sequence) -> int:
    previous = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        current = [i]
        for j, y in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[-1] + 1, previous[j - 1] + (x != y)))
        previous = current
    return previous[-1]


def error_rate(truth: str, seen: str) -> float:
    """Character error rate over whitespace-normalised text."""
    a, b = " ".join(truth.split()), " ".join(seen.split())
    return edit_distance(a, b) / max(len(a), 1)


def word_masks(words: list[OcrWord], ranges: Sequence[tuple[int, int]],
               hits: Sequence[tuple[int, int]]) -> list[int]:
    """Indices of OCR words touched by any masked character range."""
    return [
        i for i, (a, b) in enumerate(ranges)
        if any(start < b and a < end for start, end in hits)
    ]


def _raster(polys: list[np.ndarray], shape: tuple[int, int], pad: float) -> np.ndarray:
    canvas = np.zeros(shape, dtype=np.uint8)
    for poly in polys:
        centre = poly.mean(axis=0)
        grown = centre + (poly - centre) * (1 + 2 * pad / np.maximum(np.ptp(poly, axis=0), 1))
        points = np.round(grown * RASTER).astype(np.int32)
        cv2.fillPoly(canvas, [points], 1)
    return canvas


def hidden_share(box: np.ndarray, canvas: np.ndarray) -> float:
    """Share of a true word quadrilateral that lies under the mask raster."""
    stencil = np.zeros(canvas.shape, dtype=np.uint8)
    cv2.fillPoly(stencil, [np.round(box * RASTER).astype(np.int32)], 1)
    area = int(stencil.sum())
    if area == 0:
        return 1.0
    return float((stencil & canvas).sum() / area)


def audit(
    doc: Document,
    page: Page,
    matrix: np.ndarray,
    shape: tuple[int, int],
    words: list[OcrWord],
    masked: Sequence[int],
    pad_px: float,
    regions: Sequence[np.ndarray] = (),
) -> list[dict]:
    """One row per value kind, plus `_outside` and `_distractor` as share of words masked."""
    size = (int(shape[0] * RASTER) + 2, int(shape[1] * RASTER) + 2)
    polys = [np.array(words[i].poly, dtype=float) for i in masked] + list(regions)
    canvas = _raster(polys, size, pad_px)
    kept = {
        w.text.lower().strip(".,:;()") for i, w in enumerate(words) if i not in set(masked)
    }
    rows: dict[str, dict] = {}
    gold, excluded = [], []
    for span in doc.spans:
        (excluded if span.kind is None else gold).append(span)
        if span.kind in (None, "AFLEIDER"):
            continue
        row = rows.setdefault(span.kind, {"kind": span.kind, "pixel": 0, "text": 0, "total": 0})
        row["total"] += 1
        boxes = gold_boxes(page, doc, span.start, span.end)
        row["pixel"] += any(
            hidden_share(corners(b, matrix), canvas) < HIDDEN for b in boxes
        )
        tokens = [m.group().lower() for m in WORD.finditer(doc.text, span.start, span.end)]
        row["text"] += any(t in kept for t in tokens if t not in PARTICLES and len(t) > 1)
    for name, spans in (
        ("_outside", None),
        ("_distractor", [s for s in doc.spans if s.kind == "AFLEIDER"]),
    ):
        chosen = hit = 0
        for match in WORD.finditer(doc.text):
            a, b = match.start(), match.end()
            inside = any(s.start < b and a < s.end for s in doc.spans if s.kind != "AFLEIDER")
            near = any(s.start < b and a < s.end for s in doc.spans if s.kind == "AFLEIDER")
            if inside or (near if spans is None else not near):
                continue
            boxes = gold_boxes(page, doc, a, b)
            chosen += len(boxes)
            hit += sum(hidden_share(corners(x, matrix), canvas) >= 0.5 for x in boxes)
        rows[name] = {"kind": name, "pixel": hit, "text": 0, "total": chosen}
    return list(rows.values())


def truth_words(doc: Document, page: Page, matrix: np.ndarray) -> list[OcrWord]:
    """Perfect OCR: the true words at their true places, in reading order."""
    words, line, last_y = [], -1, None
    for word in page.words:
        if word.box[1] != last_y and (last_y is None or abs(word.box[1] - last_y) > 20):
            line += 1
            last_y = word.box[1]
        words.append(
            OcrWord(doc.text[word.start : word.end], corners(word.box, matrix).tolist(), 1.0, line)
        )
    return words


def redact_words(
    words: list[OcrWord], system: Ranges, repair: Callable[[str], str] | None = None
) -> tuple[list[int], str]:
    """Masked word indices and the running text. `repair` gives the system a second reading."""
    text, ranges = assemble(words)
    hits = list(system(text))
    if repair is not None:
        fixed = repair(text)
        if fixed != text:
            hits += list(system(fixed))
    return word_masks(words, ranges, hits), text
