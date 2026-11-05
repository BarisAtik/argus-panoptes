"""Image degradations for the robustness check."""

from __future__ import annotations

import io

from PIL import Image, ImageFilter


def jpeg(image: Image.Image, quality: int = 10) -> Image.Image:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    buffer.seek(0)
    return Image.open(buffer).convert("RGB")


def blur(image: Image.Image, radius: float = 3.0) -> Image.Image:
    return image.filter(ImageFilter.GaussianBlur(radius))


def downscale(image: Image.Image, factor: int = 4) -> Image.Image:
    small = image.resize((max(1, image.width // factor), max(1, image.height // factor)))
    return small.resize(image.size)


def grayscale(image: Image.Image) -> Image.Image:
    return image.convert("L").convert("RGB")


CORRUPTIONS = {"jpeg_q10": jpeg, "blur_r3": blur, "downscale_x4": downscale,
               "grayscale": grayscale}
