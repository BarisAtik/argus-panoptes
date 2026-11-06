"""Typeset a generated document as a page and remember where every character landed.

The ground truth of the study lives here. Because we draw the page ourselves, we know the exact
ink box of each word of each personal value, which no real scan can give you.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from pii_nl.evaluate import WORD
from pii_nl.generate import Document

DPI = 300
PAGE_W = 2480
MARGIN = 220
FONT_DIRS = (
    "/usr/share/fonts/truetype/liberation",
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/truetype/crosextra",
    "/usr/share/fonts/truetype/freefont",
)
# Common office looks: two serifs, two sans, one typewriter. Metric clones of familiar fonts.
FONTS = {
    "serif": "LiberationSerif-Regular.ttf",
    "sans": "LiberationSans-Regular.ttf",
    "carlito": "Carlito-Regular.ttf",
    "caladea": "Caladea-Regular.ttf",
    "mono": "LiberationMono-Regular.ttf",
}


def font_path(name: str) -> Path:
    for folder in FONT_DIRS:
        path = Path(folder) / FONTS[name]
        if path.exists():
            return path
    raise FileNotFoundError(f"{FONTS[name]}: install fonts-liberation and fonts-crosextra-carlito")


@dataclass(frozen=True)
class Word:
    """A run of non-space characters. `box` is x0, y0, x1, y1 of its ink at 300 dpi."""

    start: int
    end: int
    box: tuple[int, int, int, int]
    x_of: tuple[float, ...]  # left edge of each character, and the right edge of the last


@dataclass
class Page:
    image: Image.Image
    words: list[Word]


def _tokens(line: str, offset: int) -> list[tuple[int, int]]:
    spans, at = [], None
    for i, char in enumerate(line):
        if char.isspace():
            if at is not None:
                spans.append((offset + at, offset + i))
                at = None
        elif at is None:
            at = i
    if at is not None:
        spans.append((offset + at, offset + len(line)))
    return spans


def render_page(doc: Document, font: str = "serif", points: float = 11.0) -> Page:
    """Greedy line wrap, black on white. The page grows if a long document needs more height."""
    size = round(points * DPI / 72)
    face = ImageFont.truetype(str(font_path(font)), size)
    line_h = round(size * 1.35)
    space = face.getlength(" ")
    right = PAGE_W - MARGIN
    placed, x, y, at = [], MARGIN, MARGIN, 0
    for raw in doc.text.split("\n"):
        x = MARGIN
        for start, end in _tokens(raw, at):
            token = doc.text[start:end]
            width = face.getlength(token)
            if x > MARGIN and x + width > right:
                x, y = MARGIN, y + line_h
            placed.append((start, end, token, x, y))
            x += width + space
        y += line_h
        at += len(raw) + 1
    height = max(3508, y + MARGIN)
    image = Image.new("L", (PAGE_W, height), 255)
    draw = ImageDraw.Draw(image)
    words = []
    for start, end, token, x, y in placed:
        draw.text((x, y), token, fill=0, font=face)
        x0, y0, x1, y1 = face.getbbox(token)
        edges = tuple(x + face.getlength(token[:i]) for i in range(len(token) + 1))
        words.append(Word(start, end, (int(x + x0), y + y0, int(x + x1) + 1, y + y1), edges))
    return Page(image, words)


def gold_boxes(page: Page, doc: Document, start: int, end: int) -> list[tuple[int, int, int, int]]:
    """Ink boxes of the alphanumeric words between two character offsets. Punctuation stays out."""
    boxes = []
    for match in WORD.finditer(doc.text, start, end):
        for word in page.words:
            if word.start <= match.start() and match.end() <= word.end:
                x0 = word.x_of[match.start() - word.start]
                x1 = word.x_of[match.end() - word.start]
                boxes.append((int(x0), word.box[1], int(x1) + 1, word.box[3]))
                break
    return boxes
