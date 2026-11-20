# -*- coding: utf-8 -*-
"""Normalize approved sample cutouts to a 512x512 UI-ready asset spec."""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "assets" / "sample_cutout" / "shadow"
OUT_ROOT = ROOT / "assets" / "sample_cutout" / "final_512"
PNG_DIR = OUT_ROOT / "png"
WEBP_DIR = OUT_ROOT / "webp"
PREVIEW_DIR = ROOT / "assets" / "sample_cutout" / "preview_512"
NAMES = ["grandfather", "cottage", "tree", "cat", "car"]


def fit_square(source: Image.Image, size: int = 512, margin: float = 0.06) -> Image.Image:
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


def background(size: int, kind: str) -> Image.Image:
    if kind == "checker":
        board = Image.new("RGB", (size, size), "#f2f0eb")
        draw = ImageDraw.Draw(board)
        cell = size // 16
        for y in range(0, size, cell):
            for x in range(0, size, cell):
                if (x // cell + y // cell) % 2:
                    draw.rectangle([x, y, x + cell - 1, y + cell - 1], fill="#ddd9d1")
        return board
    return Image.new("RGB", (size, size), "#cfb08a")


def preview(asset: Image.Image, label: str, font, kind: str) -> Image.Image:
    board = background(512, kind)
    board.paste(asset, (0, 0), asset)
    draw = ImageDraw.Draw(board)
    draw.rounded_rectangle([18, 18, 188, 54], radius=18, fill=(255, 255, 255, 190))
    draw.text((32, 25), label.upper(), fill=(28, 28, 30), font=font)
    return board


def main() -> None:
    for directory in (PNG_DIR, WEBP_DIR, PREVIEW_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 18)
    except Exception:
        font = ImageFont.load_default()

    manifest = []
    for name in NAMES:
        source = Image.open(SOURCE_DIR / f"{name}.png").convert("RGBA")
        asset = fit_square(source, 512, margin=0.06)
        png_path = PNG_DIR / f"{name}.png"
        webp_path = WEBP_DIR / f"{name}.webp"
        asset.save(png_path, format="PNG", optimize=True, compress_level=9)
        asset.save(
            webp_path,
            format="WEBP",
            quality=86,
            method=6,
            alpha_quality=95,
            exact=True,
        )
        for kind in ("checker", "sand"):
            preview(asset, name, font, kind).save(
                PREVIEW_DIR / f"{name}_{kind}.png", optimize=True
            )
        manifest.append(
            {
                "name": name,
                "width": asset.width,
                "height": asset.height,
                "png": str(png_path),
                "png_bytes": png_path.stat().st_size,
                "webp": str(webp_path),
                "webp_bytes": webp_path.stat().st_size,
            }
        )

    (OUT_ROOT / "manifest.json").write_text(
        json.dumps({"size": 512, "items": manifest}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Contact sheets at 512 per cell.
    for kind, filename in (("checker", "all_512_checker.png"), ("sand", "all_512_sand.png")):
        sheet = Image.new("RGB", (1536, 1024), (232, 226, 216))
        for index, name in enumerate(NAMES):
            tile = Image.open(PREVIEW_DIR / f"{name}_{kind}.png").convert("RGB")
            sheet.paste(tile, ((index % 3) * 512, (index // 3) * 512))
        sheet.save(ROOT / "assets" / "sample_cutout" / "preview_512" / filename, optimize=True)

    print("done")


if __name__ == "__main__":
    main()
