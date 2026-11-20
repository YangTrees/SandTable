# -*- coding: utf-8 -*-
"""Quick edge-quality test for one sample: alpha matting + white-spill removal."""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from rembg import new_session, remove

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "assets" / "sample_cutout" / "source" / "cat.png"
OUT = ROOT / "assets" / "sample_cutout" / "test"


def checker(size=1024):
    im = Image.new("RGB", (size, size), "#f2f0eb")
    d = ImageDraw.Draw(im)
    for y in range(0, size, 36):
        for x in range(0, size, 36):
            if (x // 36 + y // 36) % 2:
                d.rectangle([x, y, x + 35, y + 35], fill="#ddd9d1")
    return im


def decontaminate(src: Image.Image, cut: Image.Image) -> Image.Image:
    rgb = np.asarray(src.convert("RGB"), dtype=np.float32)
    a = np.asarray(cut.getchannel("A"), dtype=np.float32) / 255.0
    # Unmix the white studio background from the semi-transparent edge pixels.
    fg = (rgb - 255.0 * (1.0 - a[..., None])) / np.maximum(a[..., None], 1e-4)
    fg = np.clip(fg, 0, 255)
    # Stronger alpha curve removes the low-opacity white fringe.
    a2 = np.clip((a - 0.06) / 0.94, 0, 1)
    rgba = np.dstack([fg, a2 * 255.0]).astype(np.uint8)
    return Image.fromarray(rgba, mode="RGBA")


def preview(cut: Image.Image, name: str):
    board = checker()
    bbox = cut.getchannel("A").getbbox()
    cut = cut.crop(bbox)
    scale = min(740 / cut.width, 740 / cut.height, 1)
    cut = cut.resize((int(cut.width * scale), int(cut.height * scale),), Image.LANCZOS)
    board.paste(cut, ((1024 - cut.width) // 2, (1024 - cut.height) // 2), cut)
    board.save(OUT / name)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    source = Image.open(SRC).convert("RGB")
    session = new_session("u2net")
    raw_bytes = remove(
        SRC.read_bytes(),
        session=session,
        alpha_matting=True,
        alpha_matting_foreground_threshold=240,
        alpha_matting_background_threshold=10,
        alpha_matting_erode_size=8,
    )
    raw = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
    raw.save(OUT / "cat_alpha_matting_raw.png")
    clean = decontaminate(source, raw)
    clean.save(OUT / "cat_alpha_matting_clean.png")
    preview(clean, "cat_alpha_matting_checker.png")
    print("done")


if __name__ == "__main__":
    main()
