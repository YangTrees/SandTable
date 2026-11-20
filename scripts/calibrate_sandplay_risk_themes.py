#!/usr/bin/env python3
"""Calibrate risk tiers, theme tags, category and one prompt in the 500-item sandplay library.

The script edits assets/sandplay_miniatures_500.json in place, refreshes all
aggregate metadata, regenerates assets/sandplay_miniatures_500.csv, and verifies
that the JSON and CSV are row-for-row consistent.
"""
from __future__ import annotations

import csv
import json
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = ROOT / "assets" / "sandplay_miniatures_500.json"
CSV_PATH = ROOT / "assets" / "sandplay_miniatures_500.csv"
BACKUP_PATH = ROOT / "assets" / "sandplay_miniatures_500.json.bak_before_calibration_20261120"

THEME_NAMES = {
    "conflict": "冲突",
    "pressure": "压力",
    "crisis": "危机",
    "shadow": "阴影",
    "transformation": "转化",
}

RISK_TO_HIGH = [
    "CRISIS_007",       # 骷髅
    "MYSTIC_012",       # 墓碑
    "CONFLICT_004",     # 匕首
    "CONFINEMENT_001",  # 铁牢笼
    "CONFINEMENT_012",  # 禁闭室
    "CONFINEMENT_017",  # 沉重镣铐
]
RISK_TO_WATCH = [
    "CRISIS_009",       # 暴风雨乌云
    "CRISIS_013",       # 烧焦的森林
]
RISK_NONE_TO_WATCH = [
    "BUILDING_069",     # 天台
    "CONFINEMENT_011",  # 铁栅栏
    "CONFINEMENT_020",  # 高墙围栏
]
SHADOW_REMOVE_IDS = (
    [f"ANIMAL_{n:03d}" for n in range(65, 73)]
    + [f"ANIMAL_{n:03d}" for n in range(75, 80)]
    + ["MYSTIC_017", "MYSTIC_026", "MYSTIC_028", "MYSTIC_029"]
)
CATEGORY_MOVE_ID = "NEUTRAL_016"
CATEGORY_TARGET = "神秘与象征符号"
PROMPT_ID = "CONFINEMENT_013"
PROMPT_SUBJECT = (
    "Subject: framed semi-transparent one-way glass partition wall, "
    "architectural mirror glass panel."
)

REQUIRED_FIELDS = [
    "id", "name", "category", "subcategory", "asset_group",
    "psychology_meaning", "supportive_hypothesis", "alternative_hypothesis",
    "verification_question", "prompt", "risk_tier", "spatial_role", "themes",
]


def load_json() -> dict[str, Any]:
    with JSON_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def aggregate(items: list[dict[str, Any]], data: dict[str, Any]) -> None:
    """Refresh aggregate metadata without changing the field schema."""
    category_counts = Counter(str(x.get("category") or "未分类") for x in items)
    for category in data.get("categories", []):
        if category["name"] in category_counts:
            category["count"] = category_counts[category["name"]]
    unknown = set(category_counts) - {c["name"] for c in data.get("categories", [])}
    if unknown:
        raise AssertionError(f"存在顶层 categories 未登记的分类: {unknown}")

    subcategory_counts = Counter(
        str(x.get("subcategory") or "").strip()
        for x in items
        if str(x.get("subcategory") or "").strip()
    )
    data["subcategory_counts"] = [
        {"name": name, "count": count}
        for name, count in sorted(subcategory_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    theme_counts = Counter(
        str(theme).strip()
        for x in items
        for theme in (x.get("themes") or [])
        if str(theme).strip()
    )
    data["theme_counts"] = {code: theme_counts[code] for code in THEME_NAMES if code in theme_counts}
    tagged = sum(1 for x in items if x.get("themes"))
    data["theme_coverage"] = tagged
    data["neutral_theme_items"] = len(items) - tagged
    data["field_coverage"] = {
        "items": len(items),
        "complete_required_items": sum(
            1 for x in items if all(k in x and (x[k] or k == "themes") for k in REQUIRED_FIELDS)
        ),
        "subcategory_items": sum(1 for x in items if x.get("subcategory")),
        "asset_group_items": sum(1 for x in items if x.get("asset_group")),
        "theme_tagged_items": tagged,
        "neutral_items": len(items) - tagged,
    }
    data["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")


def apply_changes(data: dict[str, Any]) -> dict[str, Any]:
    items = data["items"]
    by_id = {x["id"]: x for x in items}
    expected = set(RISK_TO_HIGH) | set(RISK_TO_WATCH) | set(RISK_NONE_TO_WATCH) | set(SHADOW_REMOVE_IDS)
    missing = expected - set(by_id)
    if missing:
        raise AssertionError(f"缺少目标沙具 ID: {missing}")

    before = {
        "risk_tier": dict(Counter(x.get("risk_tier") for x in items)),
        "theme_counts": dict(Counter(t for x in items for t in (x.get("themes") or []))),
        "theme_coverage": sum(1 for x in items if x.get("themes")),
        "category_counts": {c["name"]: c["count"] for c in data["categories"]},
    }
    before_records = {
        i: {
            "name": by_id[i]["name"],
            "risk_tier": by_id[i].get("risk_tier"),
            "themes": list(by_id[i].get("themes") or []),
            "category": by_id[i].get("category"),
        }
        for i in RISK_TO_HIGH + RISK_TO_WATCH + RISK_NONE_TO_WATCH + SHADOW_REMOVE_IDS + [CATEGORY_MOVE_ID]
    }
    prompt_before = by_id[PROMPT_ID].get("prompt", "")

    structure_before = {x["id"]: tuple(x.keys()) for x in items}
    style_before = {
        "style_prefix": data.get("style_prefix"),
        "style_prefix_shadow": data.get("style_prefix_shadow"),
        "style_prefix_neutral": data.get("style_prefix_neutral"),
    }

    changes: list[dict[str, Any]] = []
    for item_id in RISK_TO_HIGH:
        item = by_id[item_id]
        old = item.get("risk_tier")
        item["risk_tier"] = "high_risk"
        changes.append({"id": item_id, "field": "risk_tier", "before": old, "after": "high_risk", "name": item["name"]})
    for item_id in RISK_TO_WATCH:
        item = by_id[item_id]
        old = item.get("risk_tier")
        item["risk_tier"] = "watch"
        changes.append({"id": item_id, "field": "risk_tier", "before": old, "after": "watch", "name": item["name"]})
    for item_id in RISK_NONE_TO_WATCH:
        item = by_id[item_id]
        old = item.get("risk_tier")
        item["risk_tier"] = "watch"
        changes.append({"id": item_id, "field": "risk_tier", "before": old, "after": "watch", "name": item["name"]})

    for item_id in SHADOW_REMOVE_IDS:
        item = by_id[item_id]
        old = list(item.get("themes") or [])
        if "shadow" in old:
            item["themes"] = [t for t in old if t != "shadow"]
            changes.append({"id": item_id, "field": "themes", "before": old, "after": list(item["themes"]), "name": item["name"]})

    building = by_id["BUILDING_069"]
    old_themes = list(building.get("themes") or [])
    if "crisis" not in old_themes:
        building["themes"] = old_themes + ["crisis"]
        changes.append({"id": "BUILDING_069", "field": "themes", "before": old_themes, "after": building["themes"], "name": building["name"]})

    neutral = by_id[CATEGORY_MOVE_ID]
    old_category = neutral.get("category")
    neutral["category"] = CATEGORY_TARGET
    if old_category != CATEGORY_TARGET:
        changes.append({"id": CATEGORY_MOVE_ID, "field": "category", "before": old_category, "after": CATEGORY_TARGET, "name": neutral["name"]})

    target = by_id[PROMPT_ID]
    prompt = target.get("prompt", "")
    if "Subject:" in prompt:
        prefix = prompt.split("Subject:", 1)[0]
        target["prompt"] = prefix + PROMPT_SUBJECT
    else:
        target["prompt"] = prompt.rstrip() + " " + PROMPT_SUBJECT
    if target["prompt"] != prompt_before:
        changes.append({"id": PROMPT_ID, "field": "prompt", "before": prompt_before[-120:], "after": target["prompt"][-160:], "name": target["name"]})

    # Field schema must not change.
    structure_after = {x["id"]: tuple(x.keys()) for x in items}
    if structure_before != structure_after:
        raise AssertionError("沙具字段结构发生变化")
    if style_before["style_prefix"] != data.get("style_prefix"):
        raise AssertionError("style_prefix 被改动")
    if style_before["style_prefix_shadow"] != data.get("style_prefix_shadow"):
        raise AssertionError("style_prefix_shadow 被改动")
    if style_before["style_prefix_neutral"] != data.get("style_prefix_neutral"):
        raise AssertionError("style_prefix_neutral 被改动")

    aggregate(items, data)

    after = {
        "risk_tier": dict(Counter(x.get("risk_tier") for x in items)),
        "theme_counts": dict(Counter(t for x in items for t in (x.get("themes") or []))),
        "theme_coverage": sum(1 for x in items if x.get("themes")),
        "category_counts": {c["name"]: c["count"] for c in data["categories"]},
    }
    after_records = {
        i: {
            "name": by_id[i]["name"],
            "risk_tier": by_id[i].get("risk_tier"),
            "themes": list(by_id[i].get("themes") or []),
            "category": by_id[i].get("category"),
        }
        for i in RISK_TO_HIGH + RISK_TO_WATCH + RISK_NONE_TO_WATCH + SHADOW_REMOVE_IDS + [CATEGORY_MOVE_ID]
    }
    return {
        "before": before,
        "after": after,
        "before_records": before_records,
        "after_records": after_records,
        "changes": changes,
        "prompt_before": prompt_before,
        "prompt_after": by_id[PROMPT_ID]["prompt"],
    }


def write_json(data: dict[str, Any]) -> None:
    if not BACKUP_PATH.exists():
        shutil.copy2(JSON_PATH, BACKUP_PATH)
    tmp = JSON_PATH.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp.replace(JSON_PATH)


def expected_csv_rows(data: dict[str, Any]) -> list[list[str]]:
    rows: list[list[str]] = []
    for idx, item in enumerate(data["items"], 1):
        themes = item.get("themes") or []
        rows.append([
            str(idx),
            item.get("id", ""),
            item.get("name", ""),
            item.get("category", ""),
            item.get("subcategory", ""),
            item.get("asset_group", ""),
            item.get("legacy_category", ""),
            "|".join(themes),
            "|".join(THEME_NAMES.get(t, t) for t in themes),
            item.get("risk_tier", ""),
            item.get("spatial_role", ""),
            item.get("psychology_meaning", ""),
            item.get("supportive_hypothesis", ""),
            item.get("alternative_hypothesis", ""),
            item.get("verification_question", ""),
            str(len(item.get("psychology_meaning", "") or "")),
            str(len(item.get("prompt", "") or "")),
            item.get("prompt", ""),
            "新增100件" if item.get("legacy_category") else "旧400件",
        ])
    return rows


CSV_HEADER = [
    "序号", "ID", "名称", "一级分类", "子类", "资产组", "迁移来源", "主题编码",
    "主题名称", "风险层级", "空间角色", "心理释义", "支持性假设", "替代性假设",
    "核验问题", "释义字数", "提示词字符数", "提示词", "批次",
]


def write_csv(data: dict[str, Any]) -> list[list[str]]:
    rows = expected_csv_rows(data)
    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADER)
        writer.writerows(rows)
    return rows


def validate(data: dict[str, Any], csv_rows: list[list[str]]) -> dict[str, Any]:
    items = data["items"]
    if len(items) != 500:
        raise AssertionError(f"JSON 条数不是 500: {len(items)}")
    if len(csv_rows) != 500:
        raise AssertionError(f"CSV 数据行不是 500: {len(csv_rows)}")
    if data.get("total_count") != 500:
        raise AssertionError(f"顶层 total_count 不是 500: {data.get('total_count')}")
    ids = [x.get("id") for x in items]
    names = [x.get("name") for x in items]
    if len(set(ids)) != 500:
        raise AssertionError("存在重复 ID")
    if len(set(names)) != 500:
        raise AssertionError(f"存在重复名称: {[n for n, c in Counter(names).items() if c > 1]}")
    if sum(c.get("count", 0) for c in data.get("categories", [])) != 500:
        raise AssertionError("categories 总数之和不等于 500")
    for x in items:
        missing = [k for k in REQUIRED_FIELDS if k not in x]
        if missing:
            raise AssertionError(f"{x.get('id')} 缺少字段 {missing}")

    with CSV_PATH.open(encoding="utf-8-sig", newline="") as f:
        actual = list(csv.reader(f))
    if actual[0] != CSV_HEADER:
        raise AssertionError("CSV 表头不一致")
    expected = expected_csv_rows(data)
    if actual[1:] != expected:
        for n, (a, e) in enumerate(zip(actual[1:], expected), 1):
            if a != e:
                raise AssertionError(f"CSV 第 {n} 行与 JSON 不一致: {a[:6]} vs {e[:6]}")
        raise AssertionError("CSV 行数与 JSON 不一致")

    return {
        "json_items": len(items),
        "csv_rows": len(expected),
        "unique_ids": len(set(ids)),
        "unique_names": len(set(names)),
        "category_total": sum(c.get("count", 0) for c in data.get("categories", [])),
        "missing_fields": 0,
        "csv_json_mismatches": 0,
    }


def main() -> None:
    data = load_json()
    result = apply_changes(data)
    write_json(data)
    csv_rows = write_csv(data)
    checks = validate(data, csv_rows)
    print(json.dumps({"comparison": result, "checks": checks}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
