"""Cheap defences on top of OCR, all applied after reading the page.

`unread` is the fail-closed one: ink the reader never turned into a word gets blacked out too.
`digits` assumes that a token with many digit-like characters is a number worth hiding, whatever
the reader made of it. `lowconf` hides words the reader itself doubts. `triage` sends whole pages
to a person. Thresholds come from dev only: see `scan_nl/EVALUATION_CARD.md`.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

import cv2
import numpy as np

from .ocr import OcrWord, enhance

INK_LEVEL = 165

CONFUSABLE = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "|": "1", "S": "5", "B": "8",
                            "Z": "2", "z": "2", "D": "0", "G": "6"})
_DIGITISH = re.compile(r"[0-9OolI|SBZzDG]")


def digit_share(token: str) -> tuple[int, int]:
    """(true digits, digit-like characters) in a token."""
    return sum(c.isdigit() for c in token), len(_DIGITISH.findall(token))


def digit_masks(words: Sequence[OcrWord], digits: int, share: float) -> list[int]:
    """Words with enough true digits and mostly digit-like characters."""
    chosen = []
    for index, word in enumerate(words):
        true, like = digit_share(word.text)
        letters = sum(c.isalnum() for c in word.text)
        if true >= digits and letters and like / letters >= share:
            chosen.append(index)
    return chosen


def conf_masks(words: Sequence[OcrWord], threshold: float) -> list[int]:
    return [
        i for i, w in enumerate(words)
        if w.conf < threshold and any(c.isalnum() for c in w.text)
    ]


def unread_regions(
    image: np.ndarray, words: Sequence[OcrWord], scale: float
) -> tuple[list[np.ndarray], float]:
    """Boxes around text-like ink outside every OCR word, and that ink's share of all ink.

    A reader that drops half a page reports high confidence on the half it kept, so confidence
    can't see this failure. The ink can. `scale` is damaged pixels per pixel at 300 dpi.
    """
    flat, factor = enhance(image)
    ink = (cv2.medianBlur(flat, 3) < INK_LEVEL).astype(np.uint8)
    # Margin effects of the flattening itself sit at the very edge of the sheet.
    edge = max(int(flat.shape[0] * 0.01), 1)
    ink[:edge], ink[-edge:], ink[:, :edge], ink[:, -edge:] = 0, 0, 0, 0
    total = int(ink.sum())
    if total == 0:
        return [], 0.0
    read = np.zeros(ink.shape, dtype=np.uint8)
    pad = 8 * scale * factor
    for word in words:
        poly = np.array(word.poly, dtype=float) * factor
        centre = poly.mean(axis=0)
        grown = centre + (poly - centre) * (1 + 2 * pad / np.maximum(np.ptp(poly, axis=0), 1))
        cv2.fillPoly(read, [np.round(grown).astype(np.int32)], 1)
    left = ink & (1 - read)
    share = float(left.sum() / total)
    width = max(int(40 * scale * factor), 3)
    joined = cv2.morphologyEx(left, cv2.MORPH_CLOSE, np.ones((3, width), np.uint8))
    count, _, stats, _ = cv2.connectedComponentsWithStats(joined, connectivity=8)
    regions = []
    least_side = 10 * scale * factor
    for x, y, w, h, area in stats[1:count]:
        if w >= least_side and h >= least_side and area >= least_side * least_side:
            box = np.array([[x, y], [x + w, y], [x + w, y + h], [x, y + h]], dtype=float)
            regions.append(box / factor)
    return regions, share


def repair_digits(text: str) -> str:
    """Same length as the input. Inside number-like tokens, read O as 0 and so on, so that checked
    patterns (IBAN, BSN) get a second chance. Words without digits are left alone."""

    def fix(match: re.Match) -> str:
        token = match.group()
        true, like = digit_share(token)
        return token.translate(CONFUSABLE) if true >= 3 and like >= 0.7 * len(token) else token

    return re.sub(r"\S+", fix, text)
