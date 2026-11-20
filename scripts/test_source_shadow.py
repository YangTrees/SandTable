# -*- coding: utf-8 -*-
"""Compare a source-derived contact shadow against the synthetic one."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cutout_samples_shadow as c  # noqa: E402


def source_shadow(source: Image.Image, cut: Image.Image) -> Image.Image:
    src = np.asarray(source.convert("RGB"), dtype=np.float32) / 255.0
    alpha = np.asarray(cut.getchannel("A"), dtype=np.uint8)
    h, w = alpha.shape
    bbox = cut.getbbox()
    left, top, right, bottom = bbox
    width = right - left
    fg = alpha > 10

    min_channel = src.min(axis=2)
    darkness = np.clip((1.0 - min_channel - 0.012) / 0.985, 0.0, 1.0)

    region = np.zeros((h, w), dtype=bool)
    y0 = max(0, bottom - int((bottom - top) * 0.38))
    y1 = min(h, bottom + int((bottom - top) * 0.26))
    x0 = max(0, left - int(width * 0.18))
    x1 = min(w, right + int(width * 0.18))
    region[y0:y1, x0:x1] = True

    distance = ndimage.distance_transform_edt(~fg)
    scale = max(18.0, width * 0.085)
    weight = np.exp(-np.square(distance / scale))
    alpha_shadow = np.where((~fg) & region & (darkness > 0.018), darkness * weight * 0.86, 0.0)
    alpha_shadow = np.clip(alpha_shadow, 0, 0.46)

    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    layer.putalpha(Image.fromarray((alpha_shadow * 255).astype(np.uint8), mode="L"))
    return layer.filter(ImageFilter.GaussianBlur(radius=1.8))


def main():
    out = ROOT / "assets" / "sample_cutout" / "test"
    out.mkdir(parents=True, exist_ok=True)
    for name in ("grandfather", "cottage", "tree", "cat", "car"):
        source = Image.open(ROOT / "assets" / "sample_cutout" / "source" / f"{name}.png").convert("RGB")
        raw = Image.open(ROOT / "assets" / "sample_cutout" / "raw" / f"{name}.png").convert("RGBA")
        clean = c.decontaminate(source, raw)
        shadow = source_shadow(source, clean)
        final = c.crop_union(clean, shadow)
        final.save(out / f"{name}_source_shadow.png")
        checker = c.make_preview(final, c.checkerboard(1024), name + " src", c.ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 24))
        checker.save(out / f"{name}_source_shadow_checker.png")
        sand = c.make_preview(final, c.sand_background(1024), name + " src", c.ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 24))
        sand.save(out / f"{name}_source_shadow_sand.png")
    print("done")


if __name__ == "__main__":
    main()
