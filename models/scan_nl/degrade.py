"""Damage a page the way paper and cheap scanners do, and keep track of where the pixels went.

Each condition returns the damaged image and a 3x3 matrix from page coordinates to its pixels.
Randomness depends only on the seed passed in, so every engine sees the same damage.
"""

from __future__ import annotations

import io
from collections.abc import Callable

import cv2
import numpy as np
from PIL import Image

Step = Callable[[np.ndarray, np.ndarray, np.random.Generator], tuple[np.ndarray, np.ndarray]]


def _scale(factor: float) -> Step:
    def step(img, matrix, rng):
        out = cv2.resize(img, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA)
        return out, np.diag([factor, factor, 1.0]) @ matrix

    return step


def _rotate(degrees: float) -> Step:
    def step(img, matrix, rng):
        angle = degrees * rng.choice([-1.0, 1.0])
        h, w = img.shape[:2]
        rotation = np.vstack([cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0), [0, 0, 1]])
        out = cv2.warpAffine(
            img, rotation[:2], (w, h), flags=cv2.INTER_CUBIC, borderValue=255
        )
        return out, rotation @ matrix

    return step


def _perspective(share: float) -> Step:
    """A phone held slightly off-axis: each corner moves inward by up to `share` of the side."""

    def step(img, matrix, rng):
        h, w = img.shape[:2]
        src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
        jitter = rng.uniform(0, share, (4, 2)) * [w, h]
        dst = np.float32(src + jitter * [[1, 1], [-1, 1], [-1, -1], [1, -1]])
        warp = cv2.getPerspectiveTransform(src, dst)
        out = cv2.warpPerspective(img, warp, (w, h), flags=cv2.INTER_CUBIC, borderValue=235)
        return out, warp @ matrix

    return step


def _blur(sigma: float) -> Step:
    def step(img, matrix, rng):
        return cv2.GaussianBlur(img, (0, 0), sigma), matrix

    return step


def _noise(sigma: float, speckle: float = 0.0) -> Step:
    def step(img, matrix, rng):
        out = img.astype(np.float32) + rng.normal(0, sigma, img.shape)
        if speckle:
            mask = rng.random(img.shape) < speckle
            out[mask] = rng.choice([0.0, 255.0], int(mask.sum()))
        return np.clip(out, 0, 255).astype(np.uint8), matrix

    return step


def _jpeg(quality: int) -> Step:
    def step(img, matrix, rng):
        buffer = io.BytesIO()
        Image.fromarray(img).save(buffer, "JPEG", quality=quality)
        return np.asarray(Image.open(io.BytesIO(buffer.getvalue())).convert("L")), matrix

    return step


def _fade(contrast: float, shadow: float) -> Step:
    """Grey toner and a shadow towards one edge, as near the spine of a copied page."""

    def step(img, matrix, rng):
        h, w = img.shape[:2]
        ramp = np.linspace(1 - shadow, 1, w, dtype=np.float32)
        if rng.random() < 0.5:
            ramp = ramp[::-1]
        out = (255 - (255 - img.astype(np.float32)) * contrast) * ramp[None, :]
        return np.clip(out, 0, 255).astype(np.uint8), matrix

    return step


def _threshold(level: int) -> Step:
    def step(img, matrix, rng):
        return ((img > level) * 255).astype(np.uint8), matrix

    return step


CONDITIONS: dict[str, tuple[Step, ...]] = {
    "clean_300": (),
    "dpi_200": (_scale(2 / 3),),
    "dpi_150": (_scale(1 / 2),),
    "dpi_100": (_scale(1 / 3),),
    "blur": (_blur(2.5),),
    "noise": (_noise(35, 0.01),),
    "jpeg": (_scale(1 / 2), _jpeg(12)),
    "skew_1": (_rotate(1.0),),
    "skew_4": (_rotate(4.0),),
    "fax": (_rotate(0.5), _scale(1 / 3), _threshold(150)),
    "photocopy": (_rotate(1.5), _blur(1.2), _fade(0.65, 0.25), _noise(10), _scale(2 / 3)),
    "phone": (_perspective(0.03), _fade(0.8, 0.35), _blur(1.5), _scale(1 / 2), _jpeg(40)),
}


def apply(condition: str, image: Image.Image, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """The damaged page as a grey array, and the matrix from page coordinates to its pixels."""
    rng = np.random.default_rng(seed)
    img = np.asarray(image.convert("L"))
    matrix = np.eye(3)
    for step in CONDITIONS[condition]:
        img, matrix = step(img, matrix, rng)
    return img, matrix


def corners(box: tuple[float, float, float, float], matrix: np.ndarray) -> np.ndarray:
    """A page box as a quadrilateral in damaged pixels."""
    x0, y0, x1, y1 = box
    points = np.array([[x0, y0, 1], [x1, y0, 1], [x1, y1, 1], [x0, y1, 1]], dtype=float).T
    moved = matrix @ points
    return (moved[:2] / moved[2]).T
