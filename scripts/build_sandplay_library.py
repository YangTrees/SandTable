# -*- coding: utf-8 -*-
"""Bundle the 500 transparent sandplay assets into one browser-loadable JS file.

The workbench is opened from file://, where WebGL textures loaded from relative
file paths are blocked by the opaque origin. Embedding compressed WebP bytes as
data URIs keeps the texture path same-origin and makes the whole library usable
without running a local server.
"""
from __future__ import annotations

import base64
import io
import json
import re
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DICT = ROOT / "assets" / "sandplay_miniatures_500.json"
TRANSPARENT = ROOT / "assets" / "generated" / "transparent"
OUT = ROOT / "assets" / "generated" / "sandplay_library.js"

CATEGORY_CODES = {
    "人物与角色原型": "person_role",
    "建筑与居所": "building_home",
    "自然山水与植物": "nature_plant",
    "动物与神兽": "animal_myth",
    "交通工具与现代器物": "vehicle_tool",
    "学习与生活道具": "study_life",
    "神秘与象征符号": "mystic_symbol",
    "饮食与丰饶意象": "food_abundance",
    "攻击与对抗": "conflict_combat",
    "禁闭与学业重压": "confinement_pressure",
    "灾害与破损枯竭": "crisis_decay",
    "情绪姿态与阴影人物": "shadow_figures",
    "中性张力与转化": "neutral_transformation",
}
CATEGORY_ICONS = {
    "人物与角色原型": "🧍",
    "建筑与居所": "🏠",
    "自然山水与植物": "🌿",
    "动物与神兽": "🐾",
    "交通工具与现代器物": "🚗",
    "学习与生活道具": "📚",
    "神秘与象征符号": "✦",
    "饮食与丰饶意象": "🍎",
    "攻击与对抗": "⚔",
    "禁闭与学业重压": "⛓",
    "灾害与破损枯竭": "🏚",
    "情绪姿态与阴影人物": "◐",
    "中性张力与转化": "☯",
}


def safe_filename(value: str) -> str:
    value = re.sub(r"[^\w\-]+", "_", value, flags=re.UNICODE)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "unknown"


def find_transparent(item: dict) -> Path | None:
    code = item.get("asset_group") or CATEGORY_CODES.get(item["category"], item["id"].split("_", 1)[0].lower())
    folder = TRANSPARENT / code
    stem = f"{item['id']}_{safe_filename(item['name'])}"
    for suffix in (".webp", ".png"):
        candidate = folder / f"{stem}{suffix}"
        if candidate.exists() and candidate.stat().st_size > 1000:
            return candidate
    matches = sorted(folder.glob(f"{item['id']}_*.webp"))
    return matches[0] if matches else None


def encode_data_uri(path: Path, max_side: int = 512, quality: int = 72) -> tuple[str, int]:
    raw = path.read_bytes()
    if path.suffix.lower() == ".webp" and quality >= 86:
        return "data:image/webp;base64," + base64.b64encode(raw).decode("ascii"), len(raw)

    image = Image.open(io.BytesIO(raw)).convert("RGBA")
    if max(image.size) > max_side:
        image.thumbnail((max_side, max_side), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="WEBP", quality=quality, method=6, alpha_quality=92, exact=True)
    payload = buffer.getvalue()
    return "data:image/webp;base64," + base64.b64encode(payload).decode("ascii"), len(payload)


def main() -> int:
    payload = json.loads(DICT.read_text(encoding="utf-8"))
    items = payload.get("items", [])
    rows = []
    missing = []
    schema_issues = []
    total_bytes = 0

    required_fields = (
        "subcategory", "asset_group", "psychology_meaning",
        "supportive_hypothesis", "alternative_hypothesis",
        "verification_question", "risk_tier", "spatial_role",
    )
    for item in items:
        absent = [key for key in required_fields if not item.get(key)]
        if absent:
            schema_issues.append({"id": item.get("id"), "missing": absent})
        if "themes" not in item:
            schema_issues.append({"id": item.get("id"), "missing": ["themes"]})
        path = find_transparent(item)
        if not path:
            missing.append(item["id"])
            continue
        data_uri, size = encode_data_uri(path)
        total_bytes += size
        rows.append({
            "id": item["id"],
            "label": item["name"],
            "category": item["category"],
            "subcategory": item.get("subcategory", ""),
            "asset_group": item.get("asset_group", ""),
            "themes": item.get("themes", []),
            "risk_tier": item.get("risk_tier", "none"),
            "spatial_role": item.get("spatial_role", ""),
            "psychology_meaning": item.get("psychology_meaning", ""),
            "supportive_hypothesis": item.get("supportive_hypothesis", ""),
            "alternative_hypothesis": item.get("alternative_hypothesis", ""),
            "verification_question": item.get("verification_question", ""),
            "icon": CATEGORY_ICONS.get(item["category"], "◆"),
            "image": data_uri,
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    theme_defs = payload.get("theme_tags", [])
    theme_counts = {entry["code"]: 0 for entry in theme_defs}
    for row in rows:
        for code in row["themes"]:
            if code in theme_counts:
                theme_counts[code] += 1
    stats = {
        "items": len(rows),
        "categories": {
            entry["name"]: entry.get("count", 0)
            for entry in payload.get("categories", [])
        },
        "theme_counts": theme_counts,
        "theme_tagged_items": sum(1 for row in rows if row["themes"]),
    }
    OUT.write_text(
        "window.SANDPLAY_LIBRARY = " + body + ";\n"
        "window.SANDPLAY_LIBRARY_VERSION = '2.0';\n"
        "window.SANDPLAY_THEME_DEFS = " + json.dumps(theme_defs, ensure_ascii=False, separators=(",", ":")) + ";\n"
        "window.SANDPLAY_LIBRARY_STATS = " + json.dumps(stats, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "items": len(rows),
        "missing": len(missing),
        "missing_ids": missing[:20],
        "schema_issues": schema_issues[:20],
        "schema_issue_count": len(schema_issues),
        "encoded_bytes": total_bytes,
        "js_mb": round(OUT.stat().st_size / 1024 / 1024, 2),
        "output": str(OUT),
    }, ensure_ascii=False))
    return 0 if not missing and not schema_issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
