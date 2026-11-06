"""OCR engines behind one shape: an image goes in, words with polygons and confidences come out.

`truth` is not an engine. It returns the true words, which gives the redactor its floor: what would
leak if OCR were perfect.
"""

from __future__ import annotations

import csv
import io
import os
import subprocess
from dataclasses import asdict, dataclass

import numpy as np
from PIL import Image


@dataclass
class OcrWord:
    text: str
    poly: list[list[float]]  # four corners in image pixels
    conf: float  # 0 to 1
    line: int


def tesseract(image: np.ndarray, lang: str = "nld") -> list[OcrWord]:
    """Tesseract's own word boxes. `--psm 4` assumes one column of varied text sizes."""
    buffer = io.BytesIO()
    Image.fromarray(image).save(buffer, "PNG")
    env = {**os.environ, "OMP_THREAD_LIMIT": "1"}
    done = subprocess.run(
        ["tesseract", "stdin", "stdout", "-l", lang, "--psm", "4", "tsv"],
        input=buffer.getvalue(), capture_output=True, env=env, check=True,
    )
    return parse_tsv(done.stdout.decode("utf-8", "replace"))


def parse_tsv(tsv: str) -> list[OcrWord]:
    words, lines = [], {}
    reader = csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE)
    for row in reader:
        text = (row.get("text") or "").strip()
        if row["level"] != "5" or not text:
            continue
        key = (row["block_num"], row["par_num"], row["line_num"])
        x, y, w, h = (float(row[k]) for k in ("left", "top", "width", "height"))
        poly = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
        line = lines.setdefault(key, len(lines))
        words.append(OcrWord(text, poly, max(float(row["conf"]), 0.0) / 100, line))
    return words


def _gap_fractions(crop: np.ndarray, count: int) -> list[float] | None:
    """Centres of the `count` widest ink-free column runs inside a line crop, as shares of width."""
    if count == 0:
        return []
    import cv2

    _, ink = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    empty = (ink > 0).sum(axis=0) == 0
    runs, begin = [], None
    for x, free in enumerate(empty):
        if free and begin is None:
            begin = x
        elif not free and begin is not None:
            if begin > 0:
                runs.append((x - begin, (begin + x) / 2))
            begin = None
    if len(runs) < count:
        return None
    widest = sorted(sorted(runs, reverse=True)[:count], key=lambda r: r[1])
    return [centre / len(empty) for _, centre in widest]


def split_line(
    text: str, quad: np.ndarray, conf: float, line: int, image: np.ndarray | None = None
) -> list[OcrWord]:
    """RapidOCR reports whole lines. Find word edges at the widest gaps in the ink, if there are
    enough of them, and otherwise share the width by character count."""
    parts = text.split()
    if not parts:
        return []
    top_l, top_r, bottom_r, bottom_l = quad.astype(float)
    total = max(len(text), 1)
    edges, at = [], 0
    for part in parts:
        begin = text.index(part, at)
        at = begin + len(part)
        edges.append((begin / total, at / total))
    if image is not None and len(parts) > 1:
        import cv2

        width = max(int(np.linalg.norm(top_r - top_l)), 2)
        height = max(int(np.linalg.norm(bottom_l - top_l)), 2)
        target = np.float32([[0, 0], [width, 0], [width, height], [0, height]])
        warp = cv2.getPerspectiveTransform(np.float32(quad), target)
        crop = cv2.warpPerspective(image, warp, (width, height), borderValue=255)
        gaps = _gap_fractions(crop, len(parts) - 1)
        if gaps is not None:
            cuts = [0.0, *gaps, 1.0]
            edges = list(zip(cuts[:-1], cuts[1:]))
    words = []
    for part, (a, b) in zip(parts, edges):
        poly = [
            top_l + (top_r - top_l) * a,
            top_l + (top_r - top_l) * b,
            bottom_l + (bottom_r - bottom_l) * b,
            bottom_l + (bottom_r - bottom_l) * a,
        ]
        words.append(OcrWord(part, [[float(v) for v in p] for p in poly], float(conf), line))
    return words


_RAPID = None


def rapidocr(image: np.ndarray) -> list[OcrWord]:
    global _RAPID
    if _RAPID is None:
        from rapidocr_onnxruntime import RapidOCR

        _RAPID = RapidOCR()
    found = _RAPID(np.dstack([image] * 3))
    result = found[0] if isinstance(found, tuple) else found
    words = []
    for line, (quad, text, conf) in enumerate(result or []):
        words += split_line(text, np.array(quad, dtype=float), float(conf), line, image)
    return words


def enhance(image: np.ndarray, width: int = 2480) -> tuple[np.ndarray, float]:
    """The usual cheap clean-up: enlarge a small page to about 300 dpi, even out the lighting."""
    import cv2

    factor = max(width / image.shape[1], 1.0)
    big = cv2.resize(image, None, fx=factor, fy=factor, interpolation=cv2.INTER_CUBIC)
    background = cv2.medianBlur(cv2.resize(big, None, fx=0.1, fy=0.1), 31)
    background = cv2.resize(background, (big.shape[1], big.shape[0]))
    flat = np.clip(big.astype(np.float32) / np.maximum(background, 1) * 255, 0, 255)
    return flat.astype(np.uint8), factor


def tesseract_enhanced(image: np.ndarray) -> list[OcrWord]:
    flat, factor = enhance(image)
    words = tesseract(flat, "nld")
    for word in words:
        word.poly = [[x / factor, y / factor] for x, y in word.poly]
    return words


ENGINES = {
    "tesseract_enh": tesseract_enhanced,
    "tesseract_nld": lambda image: tesseract(image, "nld"),
    "tesseract_eng": lambda image: tesseract(image, "eng"),
    "rapidocr": rapidocr,
}


def to_json(words: list[OcrWord]) -> list[dict]:
    return [asdict(w) for w in words]


def from_json(rows: list[dict]) -> list[OcrWord]:
    return [OcrWord(**r) for r in rows]


def assemble(words: list[OcrWord]) -> tuple[str, list[tuple[int, int]]]:
    """Rebuild running text, with each word's character range.

    Lines inside a paragraph join with a space, because a hard wrap in mid-sentence is an artefact
    of layout. A newline is kept where the gap to the next line is wider than usual, and after a
    short line, so signature and address blocks stay apart as the redaction rules expect.
    """
    if not words:
        return "", []
    lines: dict[int, list[int]] = {}
    for index, word in enumerate(words):
        lines.setdefault(word.line, []).append(index)
    def top(i):
        return np.mean([words[j].poly[0][1] for j in lines[i]])

    ordered = sorted(lines, key=top)
    heights = [
        abs(words[j].poly[3][1] - words[j].poly[0][1]) for i in ordered for j in lines[i]
    ]
    typical = float(np.median(heights)) or 1.0
    widest = max(
        max(words[j].poly[1][0] for j in lines[i]) - min(words[j].poly[0][0] for j in lines[i])
        for i in ordered
    )
    parts, ranges, at = [], {}, 0
    for position, key in enumerate(ordered):
        ids = sorted(lines[key], key=lambda j: words[j].poly[0][0])
        for k, j in enumerate(ids):
            if k:
                parts.append(" ")
                at += 1
            parts.append(words[j].text)
            ranges[j] = (at, at + len(words[j].text))
            at += len(words[j].text)
        if position + 1 < len(ordered):
            gap = top(ordered[position + 1]) - top(key)
            span = max(words[j].poly[1][0] for j in ids) - min(words[j].poly[0][0] for j in ids)
            separator = "\n" if gap > 2.6 * typical or span < 0.6 * widest else " "
            parts.append(separator)
            at += 1
    return "".join(parts), [ranges[i] for i in range(len(words))]
