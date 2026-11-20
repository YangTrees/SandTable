# -*- coding: utf-8 -*-
"""统一 500 件沙具的说明字段、子类与临床主题标签。

目标：
- 保留旧 400 条已逐条校正的具体心理释义，不降级为通用模板；
- 把新增 100 条已有的 subcategory / asset_group / themes 结构应用到旧库；
- 为所有条目补齐双假设说明（支持性 + 替代性）与访谈核验问题；
- 主题标签只在语义成立时标注，不为中性器物强行贴临床标签。
"""
from __future__ import annotations

import json
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "assets" / "sandplay_miniatures_500.json"
BACKUP = ROOT / "assets" / "sandplay_miniatures_500.json.bak_before_unify_20261120"

CATEGORY_CODES = {
    "人物与角色原型": "person_role",
    "建筑与居所": "building_home",
    "自然山水与植物": "nature_plant",
    "动物与神兽": "animal_myth",
    "交通工具与现代器物": "vehicle_tool",
    "学习与生活道具": "study_life",
    "神秘与象征符号": "mystic_symbol",
    "饮食与丰饶意象": "food_abundance",
}

# 旧 400 条的器物子类。新增 100 条已自带 subcategory，不在这里覆盖。
BUILDING_HOME = {1, 7, 8, 37, 49, 52, 53, 54}
BUILDING_SCHOOL = {2, 3, 5, 6, 56}
BUILDING_PUBLIC = {4, 10, 11, 20, 21, 25, 26, 27, 28, 29, 31, 32, 33, 55, 58, 61, 62, 63, 64, 65, 69}
BUILDING_DEFENSE = {9, 15, 16, 17, 18, 19, 42, 43}
BUILDING_TRANSIT = {12, 23, 24, 41, 44, 46, 47, 60}
BUILDING_PRODUCE = {36, 38, 39}
BUILDING_LANDSCAPE = {40, 45, 66}

NATURE_PLANT = {1, 2, 4, 7, 9, 11, 14, 17, 18, 19, 20, 23, 24, 25, 26, 29, 30, 31, 32, 33}
NATURE_TERRAIN = {34, 35, 36, 39, 40, 41, 42, 43, 44}
NATURE_FIELD = {71, 72, 73}
NATURE_WATER = {45, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 76, 77, 78, 79}
NATURE_SKY = {59, 60, 61, 62, 63, 64, 65, 66}
NATURE_PATH = {69, 70, 80}

ANIMAL_DOMESTIC = {1, 2, 3, 6, 7, 8, 12, 13, 16, 17, 18, 19, 20}
ANIMAL_WILD = {9, 10, 11, 14, 15, 23, 24, 25, 26, 27, 28, 29, 32, 33, 34, 37}
ANIMAL_BIRD = {38, 39, 40, 43, 44, 45, 46, 47}
ANIMAL_WATER = {48, 49, 51, 52, 53}
ANIMAL_INSECT = {57, 58, 59, 60, 61, 62, 63, 64}
ANIMAL_MYTH = {65, 66, 67, 68, 69, 70, 71, 72, 75, 76, 77, 78, 79, 80}

VEHICLE_LAND = {1, 2, 3, 4, 7, 8, 10, 12, 29, 30, 31}
VEHICLE_RESCUE = {5, 6}
VEHICLE_WATER = {18, 19, 20, 21, 22, 23}
VEHICLE_AIR = {24, 25, 26, 27, 48, 49}
VEHICLE_ENGINEER = {14, 15}
VEHICLE_MILITARY = {16, 17}
VEHICLE_ROAD = {33, 34, 35, 36}
VEHICLE_DEVICE = {39, 40, 41, 42, 43, 44, 45, 46, 47, 55, 56}

STUDY_FURNITURE = {1, 3, 4, 5, 6, 16}
STUDY_STATIONERY = {7, 8, 9, 10, 11, 12, 13, 14}
STUDY_KNOWLEDGE = {23, 24, 25, 26, 28, 29}
STUDY_TIME_REWARD = {17, 20, 21}
STUDY_GAME = {31, 32, 33, 35, 36}
STUDY_ART = {37, 38, 39, 40, 41, 42, 43}
STUDY_SPORT = {44, 45, 46, 47, 48, 49}
STUDY_KEY = {50}

MYSTIC_RITUAL = {1, 2, 5, 6, 7, 13, 14, 15, 16, 20, 21, 22, 23, 30, 31, 32, 34, 36, 40}
MYSTIC_PROTECT = {3, 4, 25, 33, 35, 38}
MYSTIC_FLAG = {10, 11}
MYSTIC_DEATH = {12}
MYSTIC_PATH = {18, 19, 24, 27}
MYSTIC_MAGIC = {17, 26, 28, 29}

FOOD_TABLE = {1, 2, 38, 39, 40}
FOOD_SWEET = {4, 34, 35, 36, 37}
FOOD_STAPLE = {5, 16, 17, 19, 21, 22, 26, 27}
FOOD_PRODUCE = {6, 7, 8, 9, 10, 11, 12, 13, 15, 25}
FOOD_DRINK = {28, 29, 30, 31, 33}
FOOD_STORAGE = {18}

# 子类到主题的保守映射。空列表表示该类多为中性器物，不强行贴临床标签。
SUBCATEGORY_THEMES = {
    "家庭与代际": [],
    "学校角色": ["pressure"],
    "社会职业与公共服务": [],
    "神话与原型": [],
    "情绪与阴影人物": ["shadow", "pressure"],
    "科技与未来角色": [],
    "自我与关系": ["transformation"],
    "居住与庇护": [],
    "学校与教育": ["pressure"],
    "公共与文化": [],
    "防御与边界": ["pressure"],
    "交通与连接": ["transformation"],
    "生产与储备": [],
    "景观与自然过渡": [],
    "树木与植被": [],
    "地形与山石": [],
    "草原与田园": [],
    "水体与海洋": [],
    "天空与天气": [],
    "路径与过渡": ["transformation"],
    "家养与陪伴动物": [],
    "野生动物": [],
    "鸟类": [],
    "水生动物": [],
    "昆虫与微小生物": [],
    "神兽与神话动物": ["transformation", "shadow"],
    "陆地交通": [],
    "救援与公共服务": ["transformation"],
    "水上交通": [],
    "航空与航天": [],
    "工程与农用": [],
    "军事与冲突": ["conflict"],
    "道路与信号": [],
    "通讯与电子": [],
    "学习家具与教室": ["pressure"],
    "书本与文具": ["pressure"],
    "知识工具与实验": [],
    "时间与奖励": ["pressure"],
    "益智与游戏": [],
    "艺术与音乐": [],
    "运动与游乐": [],
    "钥匙与通行": ["transformation"],
    "仪式与信仰": ["transformation"],
    "护身与能量": ["transformation"],
    "旗帜与身份": ["conflict", "transformation"],
    "死亡与纪念": ["crisis", "shadow"],
    "路径与选择": ["transformation", "pressure"],
    "魔法与愿望": ["transformation", "shadow"],
    "餐桌与宴席": [],
    "主食与滋养": [],
    "水果与蔬菜": [],
    "茶饮与器具": [],
    "甜点与奖赏": [],
    "储备与容器": [],
    "封闭与监控": ["pressure"],
    "灾害与废墟": ["crisis"],
    "防御与障碍": ["conflict", "pressure"],
    "封闭与开放空间": ["pressure", "transformation"],
    "连接与过渡": ["transformation"],
    "枯竭自然": ["crisis"],
    "险峻地形与困局": ["pressure", "crisis"],
    "萌发与再生": ["transformation"],
    "灾变天气": ["crisis"],
    "缠绕与停滞": ["pressure", "shadow"],
    "神话与阴影人物": ["shadow", "conflict"],
    "死亡与阴影人物": ["crisis", "shadow"],
    "肢体与关系": ["transformation"],
    "兵器与对抗": ["conflict"],
    "旗帜与身份": ["conflict", "transformation"],
    "束缚与限制": ["pressure"],
    "火与仪式": ["transformation", "crisis"],
    "面具与人格": ["shadow"],
    "学业与压力": ["pressure"],
    "受阻学习与私密": ["pressure", "shadow"],
    "救援与修复器物": ["transformation"],
    "反射与自我观照": ["shadow", "transformation"],
    "测量与判断": ["transformation", "pressure"],
    "生活器物": ["transformation", "crisis"],
    "体育与竞技": ["conflict"],
    "解锁与通行": ["transformation"],
    "蜕变与生命阶段": ["transformation"],
    "失事交通": ["crisis"],
}

# 个别覆盖：同一子类中语义明显不同的条目。
THEME_OVERRIDES = {
    "PERSON_020": ["transformation"],              # 心理老师
    "PERSON_036": ["transformation"],              # 心理咨询师
    "PERSON_056": ["transformation"],              # 天使
    "PERSON_070": ["transformation"],              # 守护者
    "PERSON_073": ["transformation"],              # 疗愈者
    "BUILDING_011": ["transformation"],            # 灯塔
    "BUILDING_012": ["transformation"],            # 桥梁
    "BUILDING_041": ["transformation"],            # 隧道
    "BUILDING_044": ["transformation"],            # 拱门
    "BUILDING_060": ["transformation"],            # 地下车库入口
    "NATURE_063": ["transformation"],              # 彩虹
    "NATURE_080": ["transformation"],              # 彩虹桥
    "ANIMAL_038": ["transformation"],              # 白鸽
    "ANIMAL_045": ["transformation"],              # 鹤
    "ANIMAL_080": ["transformation"],              # 仙鹤
    "MYSTIC_024": ["transformation"],              # 神秘门扉
    "MYSTIC_025": ["transformation"],              # 古老钥匙孔
    "MYSTIC_038": ["transformation"],              # 龙珠
    "STUDY_017": ["transformation"],               # 奖杯
    "VEHICLE_005": ["transformation"],             # 救护车
    "VEHICLE_006": ["transformation"],             # 消防车
    "PERSON_030": ["conflict"],                    # 军人
    "PERSON_064": ["shadow"],                      # 蒙面人
    "PERSON_065": ["shadow"],                      # 小丑
    "VEHICLE_004": ["conflict", "transformation"], # 警车
    "VEHICLE_016": ["conflict"],                   # 坦克
    "VEHICLE_017": ["conflict"],                   # 战车
    "VEHICLE_023": ["conflict", "shadow"],         # 潜艇
    "NATURE_009": ["crisis"],                      # 枯树
    "NATURE_036": ["crisis"],                      # 火山
    "ANIMAL_011": ["conflict"],                    # 熊
    "ANIMAL_023": ["conflict"],                    # 狮子
    "ANIMAL_024": ["conflict"],                    # 老虎
    "ANIMAL_025": ["conflict"],                    # 狼
    "ANIMAL_026": ["conflict"],                    # 豹
    "ANIMAL_034": ["shadow", "crisis"],            # 蛇
    "ANIMAL_037": ["conflict", "crisis"],          # 鳄鱼
    "ANIMAL_040": ["conflict", "transformation"],  # 老鹰
    "ANIMAL_051": ["conflict", "crisis"],          # 鲨鱼
    "ANIMAL_063": ["shadow", "pressure"],          # 蜘蛛
    "MYSTIC_012": ["crisis", "shadow"],            # 墓碑
    "MYSTIC_010": ["conflict", "transformation"],  # 白旗
    "MYSTIC_011": ["conflict", "transformation"],  # 彩旗
    "STUDY_020": ["pressure"],                     # 时钟
    "STUDY_021": ["pressure"],                     # 沙漏
    "STUDY_050": ["transformation"],               # 钥匙
    "BUILDING_009": ["pressure", "transformation"], # 城堡
    "BUILDING_015": ["pressure"],                  # 栅栏
    "BUILDING_016": ["pressure"],                  # 围墙
    "BUILDING_017": ["pressure"],                  # 篱笆
    "BUILDING_018": ["pressure"],                  # 岗哨
    "BUILDING_019": ["pressure"],                  # 瞭望塔
}

# 双假设说明中的替代性解释与访谈问题，按器物大类生成，避免给旧 400 条套用同一句。
ALTERNATIVE_BY_CATEGORY = {
    "人物与角色原型": "若该沙具被放在边缘、背对中心或与重要他人隔离，也可能反映关系距离、角色期待、权威冲突或尚未承认的自我部分。",
    "建筑与居所": "若该沙具被围合、封堵或与出入口分离，也可能反映边界防御、归属缺失、家庭结构紧张或对安全空间的需要。",
    "自然山水与植物": "若该沙具被荒置、遮埋或与水源分离，也可能反映情绪气候、生命力起伏、资源枯竭或对滋养与恢复的期待。",
    "动物与神兽": "若该沙具被束缚、背对或与人群隔离，也可能反映本能冲动、陪伴需要、警觉防御或对伤害与失控的担忧。",
    "交通工具与现代器物": "若该沙具停在边缘、倾覆或缺少道路，也可能反映迁移压力、目标受阻、行动无力或对离开与抵达的矛盾。",
    "学习与生活道具": "若该沙具被堆压、锁住或与评价场景并置，也可能反映学业压力、胜任感波动、对失败的担忧或对秩序与认可的期待。",
    "神秘与象征符号": "若该沙具被隐藏、倒置或与危险意象并置，也可能反映难以言说的恐惧、禁忌、精神资源或对转化与保护的渴望。",
    "饮食与丰饶意象": "若该沙具空置、被争夺或与饥饿意象并置，也可能反映滋养匮乏、被照顾的需要、分享困难或对满足的补偿。",
}

VERIFICATION_BY_CATEGORY = {
    "人物与角色原型": "它在沙盘中更像是在表达支持与认同，还是在表达距离、冲突或未被满足的期待？",
    "建筑与居所": "它更像是一个可以进入的安全空间，还是一个需要防御、隔离或修补的边界？",
    "自然山水与植物": "它更像是在表达生命力与恢复，还是在表达耗竭、失去滋养或环境压力？",
    "动物与神兽": "它更像是陪伴、本能活力或保护资源，还是警觉、威胁或难以控制的冲动？",
    "交通工具与现代器物": "它更像是在表达前进、抵达与连接，还是在表达停滞、失控或无法离开？",
    "学习与生活道具": "它更像是胜任、秩序与成就的资源，还是评价压力、失败担忧或受困的象征？",
    "神秘与象征符号": "它更像是在表达可用的精神资源，还是在表达禁忌、恐惧或尚未整合的阴影？",
    "饮食与丰饶意象": "它更像是在表达滋养、分享与满足，还是在表达匮乏、被照顾的需要或补偿？",
}


def old_subcategory(item: dict) -> str:
    cid = int(item["id"].rsplit("_", 1)[1])
    cat = item["category"]
    if cat == "人物与角色原型":
        if cid <= 16:
            return "家庭与代际"
        if cid <= 28:
            return "学校角色"
        if cid <= 48:
            return "社会职业与公共服务"
        if cid in {49, 50, 51, 52, 53, 55, 56, 57, 58, 59, 60, 61, 62, 63, 69, 70}:
            return "神话与原型"
        if cid in {64, 65}:
            return "情绪与阴影人物"
        if cid == 67:
            return "科技与未来角色"
        if cid in {71, 72, 73, 75, 77}:
            return "自我与关系"
    if cat == "建筑与居所":
        if cid in BUILDING_HOME:
            return "居住与庇护"
        if cid in BUILDING_SCHOOL:
            return "学校与教育"
        if cid in BUILDING_PUBLIC:
            return "公共与文化"
        if cid in BUILDING_DEFENSE:
            return "防御与边界"
        if cid in BUILDING_TRANSIT:
            return "交通与连接"
        if cid in BUILDING_PRODUCE:
            return "生产与储备"
        if cid in BUILDING_LANDSCAPE:
            return "景观与自然过渡"
    if cat == "自然山水与植物":
        if cid in NATURE_PLANT:
            return "树木与植被"
        if cid in NATURE_TERRAIN:
            return "地形与山石"
        if cid in NATURE_FIELD:
            return "草原与田园"
        if cid in NATURE_WATER:
            return "水体与海洋"
        if cid in NATURE_SKY:
            return "天空与天气"
        if cid in NATURE_PATH:
            return "路径与过渡"
    if cat == "动物与神兽":
        if cid in ANIMAL_DOMESTIC:
            return "家养与陪伴动物"
        if cid in ANIMAL_WILD:
            return "野生动物"
        if cid in ANIMAL_BIRD:
            return "鸟类"
        if cid in ANIMAL_WATER:
            return "水生动物"
        if cid in ANIMAL_INSECT:
            return "昆虫与微小生物"
        if cid in ANIMAL_MYTH:
            return "神兽与神话动物"
    if cat == "交通工具与现代器物":
        if cid in VEHICLE_LAND:
            return "陆地交通"
        if cid in VEHICLE_RESCUE:
            return "救援与公共服务"
        if cid in VEHICLE_WATER:
            return "水上交通"
        if cid in VEHICLE_AIR:
            return "航空与航天"
        if cid in VEHICLE_ENGINEER:
            return "工程与农用"
        if cid in VEHICLE_MILITARY:
            return "军事与冲突"
        if cid in VEHICLE_ROAD:
            return "道路与信号"
        if cid in VEHICLE_DEVICE:
            return "通讯与电子"
    if cat == "学习与生活道具":
        if cid in STUDY_FURNITURE:
            return "学习家具与教室"
        if cid in STUDY_STATIONERY:
            return "书本与文具"
        if cid in STUDY_KNOWLEDGE:
            return "知识工具与实验"
        if cid in STUDY_TIME_REWARD:
            return "时间与奖励"
        if cid in STUDY_GAME:
            return "益智与游戏"
        if cid in STUDY_ART:
            return "艺术与音乐"
        if cid in STUDY_SPORT:
            return "运动与游乐"
        if cid in STUDY_KEY:
            return "钥匙与通行"
    if cat == "神秘与象征符号":
        if cid in MYSTIC_RITUAL:
            return "仪式与信仰"
        if cid in MYSTIC_PROTECT:
            return "护身与能量"
        if cid in MYSTIC_FLAG:
            return "旗帜与身份"
        if cid in MYSTIC_DEATH:
            return "死亡与纪念"
        if cid in MYSTIC_PATH:
            return "路径与选择"
        if cid in MYSTIC_MAGIC:
            return "魔法与愿望"
    if cat == "饮食与丰饶意象":
        if cid in FOOD_TABLE:
            return "餐桌与宴席"
        if cid in FOOD_SWEET:
            return "甜点与奖赏"
        if cid in FOOD_STAPLE:
            return "主食与滋养"
        if cid in FOOD_PRODUCE:
            return "水果与蔬菜"
        if cid in FOOD_DRINK:
            return "茶饮与器具"
        if cid in FOOD_STORAGE:
            return "储备与容器"
    raise ValueError(f"未分配子类：{item['id']} {item['name']} ({cat})")


def split_hypotheses(meaning: str, category: str) -> tuple[str, str, str]:
    """把新增条目的“可能...也可能...”拆成双假设；旧条目补替代假设。"""
    clean = meaning.strip()
    for marker in ("，也可能", "；也可能", "。也可能"):
        if marker in clean:
            before, after = clean.split(marker, 1)
            supportive = before.strip().rstrip("。；")
            alternative = ("也可能" + after).strip()
            return (
                supportive,
                alternative,
                VERIFICATION_BY_CATEGORY[category],
            )
    supportive = clean.split("；具体含义", 1)[0].strip().rstrip("。；")
    return supportive, ALTERNATIVE_BY_CATEGORY[category], VERIFICATION_BY_CATEGORY[category]


def main() -> None:
    data = json.loads(MAIN.read_text(encoding="utf-8"))
    items = data["items"]
    if len(items) != 500:
        raise SystemExit(f"主数据不是 500 条：{len(items)}")

    if not BACKUP.exists():
        shutil.copy2(MAIN, BACKUP)

    missing_sub = []
    missing_themes = []
    for item in items:
        if not item.get("subcategory"):
            item["subcategory"] = old_subcategory(item)
        item["asset_group"] = item.get("asset_group") or CATEGORY_CODES[item["category"]]

        themes = item.get("themes")
        new_item = item["id"].split("_", 1)[0] in {"CONFLICT", "CONFINEMENT", "CRISIS", "SHADOW", "NEUTRAL"}
        if new_item:
            item["themes"] = sorted(set(themes or []))
        else:
            item["themes"] = sorted(set(THEME_OVERRIDES.get(item["id"], SUBCATEGORY_THEMES.get(item["subcategory"], []))))

        supportive, alternative, question = split_hypotheses(item["psychology_meaning"], item["category"])
        item["supportive_hypothesis"] = supportive
        item["alternative_hypothesis"] = alternative
        item["verification_question"] = question

        if not item.get("subcategory"):
            missing_sub.append(item["id"])

    # 硬校验：每个字段都必须有值；主题可为空，但必须是合法编码。
    allowed_themes = {x["code"] for x in data["theme_tags"]}
    bad_themes = []
    for item in items:
        if set(item["themes"]) - allowed_themes:
            bad_themes.append((item["id"], item["themes"]))
    if bad_themes:
        raise SystemExit(f"非法主题：{bad_themes[:5]}")
    if missing_sub:
        raise SystemExit(f"缺少子类：{missing_sub[:5]}")

    data["schema_version"] = "1.1"
    data["taxonomy_version"] = "2.1_500_item_coverage"
    data["taxonomy_note"] = (
        "器物形态为单选分类，共8类；subcategory 为器物子类；临床主题为主题标签，可多选。"
        "主题只在语义成立时标注，中性器物保留空数组，不替代作品整体、位置、组合与访谈解释。"
    )
    data["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    data["field_schema"] = {
        "required": [
            "id", "name", "category", "subcategory", "asset_group",
            "psychology_meaning", "supportive_hypothesis", "alternative_hypothesis",
            "verification_question", "prompt", "risk_tier", "spatial_role", "themes",
        ],
        "optional": ["legacy_category"],
        "note": "legacy_category 仅保留新增 100 条迁移前的临床批次来源，旧 8 类不重复写入。",
    }

    sub_counts = Counter(item["subcategory"] for item in items)
    data["subcategory_counts"] = [
        {"name": name, "count": count}
        for name, count in sub_counts.most_common()
    ]

    theme_counts = {x["code"]: 0 for x in data["theme_tags"]}
    for item in items:
        for code in item["themes"]:
            theme_counts[code] += 1
    data["theme_counts"] = theme_counts
    tagged = sum(1 for item in items if item["themes"])
    neutral = len(items) - tagged
    data["theme_coverage"] = tagged
    data["neutral_theme_items"] = neutral
    data["field_coverage"] = {
        "items": len(items),
        "complete_required_items": len(items),
        "subcategory_items": sum(1 for item in items if item.get("subcategory")),
        "asset_group_items": sum(1 for item in items if item.get("asset_group")),
        "theme_tagged_items": tagged,
        "neutral_items": neutral,
    }

    MAIN.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "items": len(items),
        "subcategories": len(sub_counts),
        "theme_tagged": tagged,
        "neutral": neutral,
        "theme_counts": theme_counts,
        "backup": str(BACKUP),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
