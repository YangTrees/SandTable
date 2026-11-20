# -*- coding: utf-8 -*-
"""
Sample cutout test with a shadow-preserving pass.

Pipeline:
  1. rembg alpha matting extracts a clean foreground.
  2. Edge colors are decontaminated against the white studio background,
     removing the white fringe that plain rembg leaves.
  3. A source-derived contact shadow (distance-weighted) is combined with a
     low-opacity ambient ellipse so even architectural pieces sit on the sand.
"""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from rembg import new_session, remove
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "assets" / "sample_cutout" / "source"
RAW_DIR = ROOT / "assets" / "sample_cutout" / "raw"
SHADOW_DIR = ROOT / "assets" / "sample_cutout" / "shadow"
PREVIEW_DIR = ROOT / "assets" / "sample_cutout" / "preview"
NAMES = ["grandfather", "cottage", "tree", "cat", "car"]


def checkerboard(size: int) -> Image.Image:
    board = Image.new("RGB", (size, size), "#f2f0eb")
    draw = ImageDraw.Draw(board)
    cell = 36
    for y in range(0, size, cell):
        for x in range(0, size, cell):
            if (x // cell + y // cell) % 2:
                draw.rectangle([x, y, x + cell - 1, y + cell - 1], fill="#ddd9d1")
    return board


def sand_background(size: int) -> Image.Image:
    base = Image.new("RGB", (size, size), "#cfb08a")
    noise = np.random.default_rng(7).normal(0, 4.0, (size, size, 1))
    arr = np.asarray(base, dtype=np.float32) + noise
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="RGB")


def decontaminate(source: Image.Image, cut: Image.Image) -> Image.Image:
    rgb = np.asarray(source.convert("RGB"), dtype=np.float32)
    alpha = np.asarray(cut.getchannel("A"), dtype=np.float32) / 255.0
    # Recover object color from a white-background blend at soft edges.
    fg = (rgb - 255.0 * (1.0 - alpha[..., None])) / np.maximum(alpha[..., None], 1e-4)
    fg = np.clip(fg, 0, 255)
    alpha_clean = np.clip((alpha - 0.04) / 0.96, 0, 1)
    rgba = np.dstack([fg, alpha_clean * 255.0]).astype(np.uint8)
    return Image.fromarray(rgba, mode="RGBA")


def source_shadow(source: Image.Image, cut: Image.Image) -> Image.Image:
    """Use the actual studio shadow, faded with distance from the silhouette."""
    src = np.asarray(source.convert("RGB"), dtype=np.float32) / 255.0
    alpha = np.asarray(cut.getchannel("A"), dtype=np.uint8)
    h, w = alpha.shape
    bbox = cut.getbbox()
    if not bbox:
        return Image.new("RGBA", (w, h), (0, 0, 0, 0))
    left, top, right, bottom = bbox
    width = right - left
    fg = alpha > 10
    min_channel = src.min(axis=2)
    darkness = np.clip((1.0 - min_channel - 0.012) / 0.985, 0.0, 1.0)

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
    """A very soft ellipse ensures the piece does not float on uneven ground."""
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


def crop_union(cut: Image.Image, shadow: Image.Image, pad: int = 36) -> Image.Image:
    final = Image.new("RGBA", cut.size, (0, 0, 0, 0))
    final.alpha_composite(shadow)
    final.alpha_composite(cut)
    bbox = final.getchannel("A").getbbox()
    if not bbox:
        return final
    left = max(0, bbox[0] - pad)
    top = max(0, bbox[1] - pad)
    right = min(final.width, bbox[2] + pad)
    bottom = min(final.height, bbox[3] + pad)
    return final.crop((left, top, right, bottom))


def make_preview(cut: Image.Image, background: Image.Image, label: str, font) -> Image.Image:
    preview = background.copy()
    bbox = cut.getchannel("A").getbbox()
    if bbox:
        subject = cut.crop(bbox)
        scale = min(760 / subject.width, 760 / subject.height, 1.0)
        subject = subject.resize(
            (max(1, int(subject.width * scale)), max(1, int(subject.height * scale))),
            Image.LANCZOS,
        )
        x = (preview.width - subject.width) // 2
        y = (preview.height - subject.height) // 2 - 16
        preview.paste(subject, (x, y), subject)

    draw = ImageDraw.Draw(preview)
    draw.rounded_rectangle([28, 28, 238, 72], radius=22, fill=(255, 255, 255, 185))
    draw.text((46, 37), label.upper(), fill=(30, 30, 32), font=font)
    return preview


def main() -> None:
    for directory in (RAW_DIR, SHADOW_DIR, PREVIEW_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 24)
    except Exception:
        font = ImageFont.load_default()
    session = new_session("u2net")

    for name in NAMES:
        source_path = SOURCE_DIR / f"{name}.png"
        print(f"processing {name} ...", flush=True)
        source = Image.open(source_path).convert("RGB")
        raw_bytes = remove(
            source_path.read_bytes(),
            session=session,
            alpha_matting=True,
            alpha_matting_foreground_threshold=240,
            alpha_matting_background_threshold=10,
            alpha_matting_erode_size=6,
        )
        raw = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
        raw.save(RAW_DIR / f"{name}.png", optimize=True)

        clean = decontaminate(source, raw)
        shadow = compose_shadows(source, clean)
        final = crop_union(clean, shadow)
        final.save(SHADOW_DIR / f"{name}.png", optimize=True)

        checker = make_preview(final, checkerboard(1024), name, font)
        checker.save(PREVIEW_DIR / f"{name}_checker.png", optimize=True)
        sand = make_preview(final, sand_background(1024), name, font)
        sand.save(PREVIEW_DIR / f"{name}_sand.png", optimize=True)

    print("done", flush=True)


if __name__ == "__main__":
    main()
