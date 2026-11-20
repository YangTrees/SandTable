# -*- coding: utf-8 -*-
"""Shared 512x512 sandplay cutout asset specification."""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage

ASSET_SIZE = 512
ASSET_MARGIN = 0.06


def decontaminate(source: Image.Image, cut: Image.Image) -> Image.Image:
    rgb = np.asarray(source.convert("RGB"), dtype=np.float32)
    alpha = np.asarray(cut.getchannel("A"), dtype=np.float32) / 255.0
    fg = (rgb - 255.0 * (1.0 - alpha[..., None])) / np.maximum(alpha[..., None], 1e-4)
    fg = np.clip(fg, 0, 255)
    alpha_clean = np.clip((alpha - 0.04) / 0.96, 0, 1)
    rgba = np.dstack([fg, alpha_clean * 255.0]).astype(np.uint8)
    return Image.fromarray(rgba, mode="RGBA")


def source_shadow(source: Image.Image, cut: Image.Image) -> Image.Image:
    src = np.asarray(source.convert("RGB"), dtype=np.float32) / 255.0
    alpha = np.asarray(cut.getchannel("A"), dtype=np.uint8)
    h, w = alpha.shape
    bbox = cut.getbbox()
    if not bbox:
        return Image.new("RGBA", (w, h), (0, 0, 0, 0))
    left, top, right, bottom = bbox
    width = right - left
    fg = alpha > 10
    darkness = np.clip((1.0 - src.min(axis=2) - 0.012) / 0.985, 0.0, 1.0)
    region = np.zeros((h, w), dtype=bool)
    y0 = max(0, bottom - int((bottom - top) * 0.40))
    y1 = min(h, bottom + int((bottom - top) * 0.30))
    x0 = max(0, left - int(width * 0.22))
    x1 = min(w, right + int(width * 0.22))
    region[y0:y1, x0:x1] = True
    distance = ndimage.distance_transform_edt(~fg)
    scale = max(20.0, width * 0.13)
    weight = np.exp(-np.square(distance / scale))
    alpha_shadow = np.where((~fg) & region & (darkness > 0.018), darkness * weight * 0.82, 0.0)
    alpha_shadow = np.clip(alpha_shadow, 0, 0.46)
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    layer.putalpha(Image.fromarray((alpha_shadow * 255).astype(np.uint8), mode="L"))
    return layer.filter(ImageFilter.GaussianBlur(radius=1.8))


def ambient_shadow(cut: Image.Image) -> Image.Image:
    bbox = cut.getbbox()
    shadow = Image.new("RGBA", cut.size, (0, 0, 0, 0))
    if not bbox:
        return shadow
    left, top, right, bottom = bbox
    width = right - left
    height = max(12, min(42, int((bottom - top) * 0.045)))
    cx = (left + right) / 2 + width * 0.02
    cy = bottom - height * 0.18
    draw = ImageDraw.Draw(shadow)
    draw.ellipse(
        [cx - width * 0.52, cy - height * 0.58, cx + width * 0.52, cy + height * 0.80],
        fill=(0, 0, 0, 42),
    )
    return shadow.filter(ImageFilter.GaussianBlur(radius=max(10, int(width * 0.04))))


def compose_shadows(source: Image.Image, cut: Image.Image) -> Image.Image:
    shadow = Image.new("RGBA", cut.size, (0, 0, 0, 0))
    shadow.alpha_composite(ambient_shadow(cut))
    shadow.alpha_composite(source_shadow(source, cut))
    return shadow


def fit_square(source: Image.Image, size: int = ASSET_SIZE, margin: float = ASSET_MARGIN) -> Image.Image:
    image = source.convert("RGBA")
    bbox = image.getchannel("A").getbbox()
    if bbox:
        image = image.crop(bbox)
    max_side = max(1, int(size * (1.0 - margin * 2.0)))
    scale = min(max_side / image.width, max_side / image.height, 1.0)
    image = image.resize(
        (max(1, int(image.width * scale)), max(1, int(image.height * scale))),
        Image.LANCZOS,
    )
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.alpha_composite(image, ((size - image.width) // 2, (size - image.height) // 2))
    return canvas


def encode_png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True, compress_level=9)
    return buffer.getvalue()


def encode_webp(image: Image.Image, quality: int = 86) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="WEBP", quality=quality, method=6, alpha_quality=95, exact=True)
    return buffer.getvalue()
