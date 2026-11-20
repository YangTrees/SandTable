# -*- coding: utf-8 -*-
"""从 500 件沙具中删除 100 件冗余/抽象/低投射条目，保留 400 件并升级字段。"""
from __future__ import annotations

import json
import shutil
from collections import Counter, OrderedDict
from pathlib import Path

ROOT = Path(r"D:\AI\AI_SandBox")
MAIN = ROOT / "assets" / "sandplay_miniatures_500.json"
BACKUP = MAIN.with_name("sandplay_miniatures_500.json.bak_before_cleanup_20261120")
DELETED_JSON = ROOT / "assets" / "sandplay_miniatures_deleted_100.json"
DELETED_MD = ROOT / "assets" / "sandplay_miniatures_deleted_100.md"

DELETE_GROUPS = [
    ("完全重名，保留同名另一条", ["NATURE_074", "NATURE_075", "FOOD_032", "VEHICLE_050"]),
    ("抽象关系或天气概念，难稳定具象为单一微缩手办", [
        "PERSON_074", "PERSON_076", "PERSON_079", "PERSON_080",
        "NATURE_067", "NATURE_068",
        "BUILDING_050", "BUILDING_051", "BUILDING_067", "BUILDING_068",
    ]),
    ("日常家电、主食蔬菜或低投射价值凑数项", [
        "VEHICLE_051", "VEHICLE_052", "VEHICLE_053", "VEHICLE_054",
        "VEHICLE_057", "VEHICLE_058", "VEHICLE_059", "VEHICLE_060",
        "FOOD_020", "FOOD_024", "FOOD_023",
    ]),
    ("角色高度重叠，保留同类代表", ["PERSON_031", "PERSON_032", "PERSON_054", "PERSON_078"]),
    ("同类节庆食物重叠，保留生日蛋糕", ["FOOD_003"]),
    ("人物角色功能重复或投射价值较低", [
        "PERSON_021", "PERSON_039", "PERSON_040", "PERSON_042",
        "PERSON_048", "PERSON_063", "PERSON_066", "PERSON_068",
    ]),
    ("桥梁形态重叠，保留主桥", ["BUILDING_013", "BUILDING_014"]),
    ("交通站点重复，保留机场与码头", ["BUILDING_022", "BUILDING_057", "BUILDING_059"]),
    ("塔楼类重复，保留灯塔、高塔与瞭望塔", ["BUILDING_034", "BUILDING_035", "BUILDING_070"]),
    ("门类重复，保留城门与拱门", ["BUILDING_030", "BUILDING_048"]),
    ("树木形态高度重叠", [
        "NATURE_003", "NATURE_005", "NATURE_006", "NATURE_008", "NATURE_010",
        "NATURE_012", "NATURE_013", "NATURE_015", "NATURE_016",
    ]),
    ("花卉形态高度重叠", ["NATURE_021", "NATURE_022"]),
    ("地被植物重复", ["NATURE_027", "NATURE_028"]),
    ("山石形态重复", ["NATURE_037", "NATURE_038"]),
    ("半岛与岛屿或海岸重复", ["NATURE_046"]),
    ("小型宠物重复", ["ANIMAL_004", "ANIMAL_005"]),
    ("家禽重复", ["ANIMAL_021", "ANIMAL_022"]),
    ("大型草食动物重复", ["ANIMAL_030", "ANIMAL_031"]),
    ("爬行或两栖类重复", ["ANIMAL_035", "ANIMAL_036"]),
    ("小型鸟类重复", ["ANIMAL_041", "ANIMAL_042"]),
    ("龟类重复", ["ANIMAL_050"]),
    ("小型海洋生物重复", ["ANIMAL_054", "ANIMAL_055", "ANIMAL_056"]),
    ("神兽近义重复", ["ANIMAL_073", "ANIMAL_074"]),
    ("交通工具类型重复", ["VEHICLE_009", "VEHICLE_011", "VEHICLE_013"]),
    ("慢速飞行或缆索类重复", ["VEHICLE_028", "VEHICLE_032"]),
    ("补给设施重复", ["VEHICLE_037", "VEHICLE_038"]),
    ("书桌重复", ["STUDY_002"]),
    ("文具收纳低投射价值", ["STUDY_015"]),
    ("奖状、奖牌与奖杯重叠", ["STUDY_018", "STUDY_019"]),
    ("时间工具重复", ["STUDY_022"]),
    ("光学工具重复", ["STUDY_027"]),
    ("实验器具重复", ["STUDY_030"]),
    ("棋类重复", ["STUDY_034"]),
    ("旗帜类重复", ["MYSTIC_008", "MYSTIC_009"]),
    ("水晶或能量石重复", ["MYSTIC_037", "MYSTIC_039"]),
    ("水果近义精简", ["FOOD_014"]),
]

RISK = {
    "VEHICLE_016": "high_risk",  # 坦克
    "VEHICLE_017": "high_risk",  # 战车
    "MYSTIC_012": "watch",       # 墓碑
    "NATURE_036": "watch",       # 火山
    "ANIMAL_034": "watch",       # 蛇
    "ANIMAL_063": "watch",       # 蜘蛛
    "NATURE_009": "watch",       # 枯树
}

DEFAULT_ROLE = {
    "人物与角色原型": "self_proxy",
    "建筑与居所": "container",
    "自然山水与植物": "resource",
    "动物与神兽": "symbol",
    "交通工具与现代器物": "connector",
    "学习与生活道具": "resource",
    "神秘与象征符号": "symbol",
    "饮食与丰饶意象": "resource",
}

ROLE_OVERRIDES = {
    "container": {
        # 建筑
        "BUILDING_001", "BUILDING_002", "BUILDING_003", "BUILDING_005",
        "BUILDING_006", "BUILDING_007", "BUILDING_008", "BUILDING_020",
        "BUILDING_021", "BUILDING_028", "BUILDING_029", "BUILDING_037",
        "BUILDING_045", "BUILDING_052", "BUILDING_053", "BUILDING_054",
        "BUILDING_056", "BUILDING_061", "BUILDING_062", "BUILDING_066",
        # 自然
        "NATURE_045", "NATURE_047", "NATURE_051", "NATURE_053", "NATURE_076",
        # 交通工具
        "VEHICLE_019", "VEHICLE_020", "VEHICLE_030", "VEHICLE_031",
        # 学习
        "STUDY_001", "STUDY_003", "STUDY_016", "STUDY_039",
        # 神秘
        "MYSTIC_003", "MYSTIC_004", "MYSTIC_016", "MYSTIC_026",
        "MYSTIC_030", "MYSTIC_031",
        # 饮食
        "FOOD_001", "FOOD_002", "FOOD_006", "FOOD_018", "FOOD_028",
        "FOOD_029", "FOOD_030", "FOOD_031", "FOOD_033", "FOOD_034",
        "FOOD_035", "FOOD_036", "FOOD_037", "FOOD_038", "FOOD_039",
        "FOOD_040",
    },
    "barrier": {
        "BUILDING_009", "BUILDING_015", "BUILDING_016", "BUILDING_017",
        "BUILDING_018", "BUILDING_019", "BUILDING_040", "BUILDING_042",
        "BUILDING_043",
        "NATURE_034", "NATURE_035", "NATURE_039", "NATURE_040",
        "NATURE_042", "NATURE_043", "NATURE_071", "NATURE_079",
        "STUDY_013",
        "MYSTIC_018", "MYSTIC_025",
    },
    "connector": {
        "BUILDING_012", "BUILDING_023", "BUILDING_024", "BUILDING_041",
        "BUILDING_044", "BUILDING_046", "BUILDING_047", "BUILDING_049",
        "BUILDING_060",
        "NATURE_048", "NATURE_049", "NATURE_069", "NATURE_070", "NATURE_080",
        "STUDY_023", "STUDY_024", "STUDY_050",
        "MYSTIC_024",
        "ANIMAL_038", "ANIMAL_047",
    },
    "threat": {
        "NATURE_036", "NATURE_054", "NATURE_066",
        "ANIMAL_011", "ANIMAL_023", "ANIMAL_024", "ANIMAL_025",
        "ANIMAL_026", "ANIMAL_034", "ANIMAL_037", "ANIMAL_040",
        "ANIMAL_051", "ANIMAL_063",
        "VEHICLE_016", "VEHICLE_017", "VEHICLE_023",
    },
    "resource": {
        "BUILDING_004", "BUILDING_025", "BUILDING_026", "BUILDING_036",
        "BUILDING_038", "BUILDING_039",
        "ANIMAL_016", "ANIMAL_017", "ANIMAL_018", "ANIMAL_019", "ANIMAL_020",
        "VEHICLE_005", "VEHICLE_006", "VEHICLE_014", "VEHICLE_015",
        "VEHICLE_021", "VEHICLE_041", "VEHICLE_042", "VEHICLE_055",
        "MYSTIC_033", "MYSTIC_038", "MYSTIC_040",
    },
    "symbol": {
        "BUILDING_010", "BUILDING_011", "BUILDING_027", "BUILDING_031",
        "BUILDING_032", "BUILDING_033", "BUILDING_055", "BUILDING_063",
        "BUILDING_064", "BUILDING_065", "BUILDING_069",
        "NATURE_009", "NATURE_059", "NATURE_060", "NATURE_061",
        "NATURE_062", "NATURE_063", "NATURE_064", "NATURE_065",
        "STUDY_004", "STUDY_005", "STUDY_006", "STUDY_017", "STUDY_020",
        "STUDY_021", "STUDY_040", "STUDY_041", "STUDY_042", "STUDY_043",
        "STUDY_047",
        "VEHICLE_026", "VEHICLE_027", "VEHICLE_043", "VEHICLE_045",
        "VEHICLE_046", "VEHICLE_047", "VEHICLE_049", "VEHICLE_056",
        "FOOD_004",
    },
}


def build_delete_map(items_by_id: dict[str, dict]) -> dict[str, str]:
    reasons: dict[str, str] = {}
    for reason, ids in DELETE_GROUPS:
        for item_id in ids:
            if item_id in reasons:
                raise SystemExit(f"删除项重复：{item_id}")
            if item_id not in items_by_id:
                raise SystemExit(f"删除项不存在：{item_id}")
            reasons[item_id] = reason
    if len(reasons) != 100:
        raise SystemExit(f"删除数量不是 100：{len(reasons)}")
    return reasons


def spatial_role(item: dict) -> str:
    item_id = item["id"]
    role = next((name for name, ids in ROLE_OVERRIDES.items() if item_id in ids), None)
    if role is None:
        role = DEFAULT_ROLE[item["category"]]
    assert role in {"self_proxy", "container", "barrier", "connector", "threat", "resource", "symbol"}
    return role


def main() -> None:
    original_text = MAIN.read_text(encoding="utf-8")
    data = json.loads(original_text, object_pairs_hook=OrderedDict)
    items = data["items"]
    if len(items) != 500:
        raise SystemExit(f"当前条目数不是 500：{len(items)}")

    items_by_id = {item["id"]: item for item in items}
    reasons = build_delete_map(items_by_id)

    before_style = data["style_prefix"]
    before_prompts = {item["id"]: item["prompt"] for item in items}
    before_ids = set(items_by_id)

    if not BACKUP.exists():
        shutil.copy2(MAIN, BACKUP)

    kept = [item for item in items if item["id"] not in reasons]
    removed = [item for item in items if item["id"] in reasons]
    if len(kept) != 400 or len(removed) != 100:
        raise SystemExit(f"清洗后数量异常：kept={len(kept)} removed={len(removed)}")

    # 保留顺序、prompt、style_prefix；仅新增字段。
    for item in kept:
        item["risk_tier"] = RISK.get(item["id"], "none")
        item["spatial_role"] = spatial_role(item)

    data["items"] = kept
    data["total_count"] = len(kept)
    counts = Counter(item["category"] for item in kept)
    for category in data["categories"]:
        actual = counts[category["name"]]
        if category.get("count") != actual:
            category["count"] = actual
    if data.get("meaning_revision"):
        data["meaning_revision"]["revised_count"] = len(kept)

    # 硬校验：顶层风格与所有保留条目的 prompt 均未变化。
    if data["style_prefix"] != before_style:
        raise SystemExit("style_prefix 被意外修改")
    for item in kept:
        if item["prompt"] != before_prompts[item["id"]]:
            raise SystemExit(f"prompt 被意外修改：{item['id']}")
    if set(item["id"] for item in kept) | set(reasons) != before_ids:
        raise SystemExit("ID 集合不闭合")

    MAIN.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    deleted_payload = {
        "deleted_count": len(removed),
        "remaining_count": len(kept),
        "deleted_at": "2026-11-20",
        "items": [
            {
                "id": item["id"],
                "name": item["name"],
                "category": item["category"],
                "reason": reasons[item["id"]],
            }
            for item in removed
        ],
    }
    DELETED_JSON.write_text(
        json.dumps(deleted_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# 沙具删除清单（100 件）",
        "",
        "| 序号 | ID | 名称 | 类别 | 删除理由 |",
        "| ---: | --- | --- | --- | --- |",
    ]
    for index, item in enumerate(removed, 1):
        lines.append(
            f"| {index} | `{item['id']}` | {item['name']} | {item['category']} | {reasons[item['id']]} |"
        )
    DELETED_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"kept={len(kept)} removed={len(removed)}")
    print("category_counts", dict((c["name"], c["count"]) for c in data["categories"]))
    print("risk_counts", dict(Counter(item["risk_tier"] for item in kept)))
    print("role_counts", dict(Counter(item["spatial_role"] for item in kept)))
    print(f"deleted_json={DELETED_JSON}")
    print(f"deleted_md={DELETED_MD}")
    print(f"backup={BACKUP}")


if __name__ == "__main__":
    main()
