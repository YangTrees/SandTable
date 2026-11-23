from __future__ import annotations

import asyncio
import base64
import json
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

import httpx

from .config import (
    ALLOW_DEMO_REPORT,
    MULTIMODAL_API_KEY,
    MULTIMODAL_BASE_URL,
    MULTIMODAL_MODEL,
    MULTIMODAL_TIMEOUT_SECONDS,
)
from .demo_report import build_demo_report
from .holistic import (
    HOLISTIC_SCREEN_PROMPT,
    is_high_risk,
    normalize_screen,
    screen_triggers,
    visual_high_objects,
    visual_risk_triggers,
    visual_watch_objects,
)
from .prompt import SYSTEM_PROMPT, build_user_prompt
from .quality import (
    QUALITY_FLAG_META,
    build_assessment_basis,
    build_sample_quality,
    structured_academic_scores,
    terrain_observation,
)
from .process_metrics import (
    build_process_analysis,
    build_process_metrics,
    has_process_data,
    process_note,
    process_telemetry,
)
from .schemas import ReportEnvelope
from .theory import (
    CHAPTER_TITLES,
    PROTECTIVE_CHAPTER_TITLE,
    RISK_DIMENSIONS,
    RISK_INSTRUMENTS,
    SIX_DIMENSION_THEORIES,
    SIX_DIMENSIONS,
    TRAINING_MODULES,
)
from .utils import clean_json_text, parse_json_object


def _data_uri(content: bytes, filename: str | None) -> str:
    filename = (filename or "").lower()
    mime = "image/png"
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        mime = "image/png"
    elif content[:3] == b"\xff\xd8\xff":
        mime = "image/jpeg"
    elif content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        mime = "image/webp"
    elif filename.endswith((".jpg", ".jpeg")):
        mime = "image/jpeg"
    elif filename.endswith(".webp"):
        mime = "image/webp"
    return f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}"


def _chapter_list(report: dict[str, Any], key: str, field: str) -> list[dict[str, Any]]:
    chapter = report.get(key)
    if not isinstance(chapter, dict):
        return []
    rows = chapter.get(field)
    return rows if isinstance(rows, list) else []


_MODULE_PREFIX_RE = re.compile(r"^模块[一二三四五六七八九十0-9]+[：:]?\s*")


def _normalize_fixed_name(value: Any) -> str:
    name = _MODULE_PREFIX_RE.sub("", str(value or "").strip())
    return re.sub(r"\s+", "", name).replace("（", "(").replace("）", ")")


_MODULE_ALIASES: dict[str, tuple[str, ...]] = {
    "模块一：专注力与沉浸训练（心流模块）": ("专注力", "沉浸", "心流"),
    "模块二：逻辑思维与结构化表达训练": ("逻辑思维", "结构化表达"),
    "模块三：空间认知与学习策略迁移训练": ("空间认知", "学习策略", "迁移训练"),
    "模块四：人际互动与情绪表达训练": ("人际互动", "情绪表达"),
    "模块五：目标管理与学业规划训练": ("目标管理", "学业规划"),
    "模块六：家庭协同与亲子沟通训练（家长侧）": ("家庭协同", "亲子沟通", "家长"),
}

_EXPLORATION_DISCLAIMER = "以上为基于沙盘与现有线索的探索性推断，需结合后续成绩与访谈核验。"
_EXPLORATION_SUFFIX_MARKERS = (
    "成绩与访谈核验", "后续成绩", "访谈核验", "探索性推断",
)
_EXPLORATION_BLOCKERS = (
    "无法判定", "无足够线索", "缺少足够线索", "暂不对", "不能替代",
    "无法形成", "缺少成绩数据", "不足以判定", "不作强弱判定",
)
_RISK_RANK = {"L1": 1, "L2": 2, "L3": 3, "L4": 4}
_L4_TEXT_RE = re.compile(
    r"(自杀|自伤|不想活|活着没意思|死了算了|结束生命|跳楼|割腕|服毒|"
    r"永远离开|撑不下去|没有活下去|彻底绝望)"
)
_L3_TEXT_RE = re.compile(
    r"(霸凌|欺凌|校园暴力|被孤立|遭排挤|威胁|勒索|重大变故|家庭变故|"
    r"父母离异|亲人去世|亲人离世|拒绝交流|不愿交流|完全不沟通|拒绝说话)"
)
_DESTRUCTION_TEXT_RE = re.compile(
    r"(掩埋|埋掉|埋起来|埋进|埋入|推倒|砸碎|砸毁|摧毁|烧掉|焚烧|铲平|挖掉|丢弃|扔掉)"
)
_DEATH_ITEM_WORDS = ("骷髅", "墓碑", "棺材", "尸体", "遗照", "坟墓")
_HIGH_RISK_ITEM_WORDS = _DEATH_ITEM_WORDS + ("匕首", "铁牢笼", "禁闭室", "镣铐")


def _has_exploration_disclaimer(text: str) -> bool:
    """判断结论是否已有探索性核验后缀，避免模型改写后重复追加。"""
    normalized = re.sub(r"\s+", "", str(text or ""))
    if _EXPLORATION_DISCLAIMER in normalized:
        return True
    tail = normalized[-160:]
    return any(marker in tail for marker in _EXPLORATION_SUFFIX_MARKERS)


def _dedupe_exploration_disclaimer(text: str) -> str:
    """清除连续或分散出现的重复免责声明。"""
    value = str(text or "")
    value = re.sub(
        rf"(?:\s*{re.escape(_EXPLORATION_DISCLAIMER)})+",
        _EXPLORATION_DISCLAIMER,
        value,
    )
    while value.count(_EXPLORATION_DISCLAIMER) > 1:
        value = value.replace(_EXPLORATION_DISCLAIMER, "", 1)
    return value


def _ordered_fixed_rows(
    rows: list[dict[str, Any]],
    expected_names: list[str],
    label: str,
    aliases: dict[str, tuple[str, ...]] | None = None,
) -> list[dict[str, Any]]:
    """按固定名称清单重排，允许模型改变输出顺序或省略“模块X：”前缀。"""
    if len(rows) != len(expected_names):
        raise ValueError(f"{label} 必须恰好 {len(expected_names)} 项")

    expected_by_norm = {_normalize_fixed_name(name): name for name in expected_names}
    matched: dict[str, dict[str, Any]] = {}
    unmatched: list[dict[str, Any]] = []
    for row in rows:
        norm = _normalize_fixed_name(row.get("name"))
        canonical = expected_by_norm.get(norm)
        if canonical and canonical not in matched:
            matched[canonical] = row
        else:
            unmatched.append(row)

    for row in list(unmatched):
        norm = _normalize_fixed_name(row.get("name"))
        candidates = []
        for expected in expected_names:
            if expected in matched:
                continue
            expected_norm = _normalize_fixed_name(expected)
            if norm and (norm in expected_norm or expected_norm in norm):
                candidates.append(expected)
        if len(candidates) == 1:
            matched[candidates[0]] = row
            unmatched.remove(row)
            continue
        candidates = []
        for expected in expected_names:
            if expected in matched:
                continue
            keywords = (aliases or {}).get(expected) or ()
            if keywords and any(keyword in norm for keyword in keywords):
                candidates.append(expected)
        if len(candidates) == 1:
            matched[candidates[0]] = row
            unmatched.remove(row)

    missing = [name for name in expected_names if name not in matched]
    extra = [str(row.get("name") or "") for row in unmatched]
    if missing or extra:
        detail = []
        if missing:
            detail.append("缺少 " + "、".join(missing))
        if extra:
            detail.append("多出 " + "、".join(extra))
        raise ValueError(f"{label} 名称不符合固定清单：" + "；".join(detail))

    ordered = []
    for name in expected_names:
        row = matched[name]
        row["name"] = name
        ordered.append(row)
    return ordered


def _repair_training_modules(
    rows: list[dict[str, Any]], expected_names: list[str]
) -> list[dict[str, Any]]:
    """模型偶发漏项时补齐六个固定模块，避免整份报告生成失败。"""
    expected_by_norm = {_normalize_fixed_name(name): name for name in expected_names}
    matched: dict[str, dict[str, Any]] = {}
    unmatched: list[dict[str, Any]] = []
    for row in rows:
        norm = _normalize_fixed_name(row.get("name"))
        canonical = expected_by_norm.get(norm)
        if canonical and canonical not in matched:
            matched[canonical] = row
        else:
            unmatched.append(row)

    for row in list(unmatched):
        norm = _normalize_fixed_name(row.get("name"))
        candidates = [
            expected for expected in expected_names
            if expected not in matched
            and norm
            and (norm in _normalize_fixed_name(expected) or _normalize_fixed_name(expected) in norm)
        ]
        if len(candidates) == 1:
            matched[candidates[0]] = row
            unmatched.remove(row)
            continue
        candidates = [
            expected for expected in expected_names
            if expected not in matched
            and any(keyword in norm for keyword in (_MODULE_ALIASES.get(expected) or ()))
        ]
        if len(candidates) == 1:
            matched[candidates[0]] = row
            unmatched.remove(row)

    module_keys = {name: key for key, name in TRAINING_MODULES}
    for name in expected_names:
        if name in matched:
            continue
        matched[name] = {
            "key": module_keys.get(name, ""),
            "name": name,
            "goals": ["围绕该维度设置循序渐进的观察与练习目标。"],
            "dimensions": [],
            "logic": "该模块由系统按固定六模块结构补位，具体训练逻辑待访谈与补充观察后细化。",
            "format": "待定",
            "teacher_actions": [],
            "parent_actions": [],
            "student_actions": [],
            "active": False,
            "deferred": True,
            "placeholder": True,
        }
    ordered = []
    for name in expected_names:
        row = matched[name]
        row["name"] = name
        ordered.append(row)
    return ordered


def validate_report(report: dict[str, Any]) -> dict[str, Any]:
    """严格校验九章节、六维、九维风险、六训练模块。"""
    if not isinstance(report, dict):
        raise ValueError("报告根节点必须是 JSON 对象")
    if isinstance(report.get("report"), dict):
        report = report["report"]
    report = ReportEnvelope.model_validate(report).model_dump()

    six = _chapter_list(report, "chapter_3_six_dimensions", "dimensions")
    expected_six = [name for _, name in SIX_DIMENSIONS]
    report["chapter_3_six_dimensions"]["dimensions"] = _ordered_fixed_rows(
        six, expected_six, "chapter_3_six_dimensions.dimensions"
    )

    risk = _chapter_list(report, "chapter_5_risk", "dimensions")
    expected_risk = [name for _, name in RISK_DIMENSIONS]
    report["chapter_5_risk"]["dimensions"] = _ordered_fixed_rows(
        risk, expected_risk, "chapter_5_risk.dimensions"
    )
    if report["chapter_5_risk"].get("visibility") != "counselor_only":
        raise ValueError("第五章必须标记 counselor_only")

    modules = _chapter_list(report, "chapter_8_training_modules", "modules")
    expected_modules = [name for _, name in TRAINING_MODULES]
    report["chapter_8_training_modules"]["modules"] = _repair_training_modules(modules, expected_modules)

    for key, title in CHAPTER_TITLES.items():
        chapter = report.get(key)
        if not isinstance(chapter, dict):
            raise ValueError(f"缺少 {key}")
        chapter.setdefault("title", title)
    return report


def _process_telemetry(payload: dict[str, Any]) -> dict[str, Any]:
    return process_telemetry(payload)


def _has_process_data(payload: dict[str, Any]) -> bool:
    return has_process_data(payload)


def _process_note(payload: dict[str, Any]) -> str:
    return process_note(payload)


def _raw_record_echo(payload: dict[str, Any]) -> dict[str, str]:
    return {
        "sandplay_description": str(payload.get("sandplay_description") or ""),
        "self_narrative": str(payload.get("self_narrative") or ""),
        "teacher_observation": str(payload.get("teacher_observation") or ""),
    }


def _report_basis(payload: dict[str, Any], transcript_url: str | None) -> list[str]:
    return build_assessment_basis(payload, transcript_url)


def _canonical_dimension_name(value: Any, expected_names: list[str]) -> str:
    text = re.sub(r"（维度[0-9一二三四五六七八九十]+）", "", str(value or ""))
    text = re.sub(r"\(维度[0-9一二三四五六七八九十]+\)", "", text)
    text = re.sub(r"维度[0-9一二三四五六七八九十]+", "", text).strip()
    for name in expected_names:
        if name in text or text in name:
            return name
    return ""


def _module_short_name(name: Any) -> str:
    text = str(name or "").strip()
    return text.split("：", 1)[0] if "：" in text else text


def _module_display_name(name: Any) -> str:
    """把“模块一：专注力与沉浸训练（心流模块）”收束为“模块一（专注力与沉浸训练）”。"""
    text = str(name or "").strip()
    match = re.match(r"(模块[一二三四五六])(?:：|:)(.+)", text)
    if not match:
        return _module_short_name(text)
    detail = re.sub(r"（[^）]*）$", "", match.group(2).strip()).strip()
    return f"{match.group(1)}（{detail}）" if detail else match.group(1)


def _risk_dimension_levels(report: dict[str, Any]) -> dict[str, str]:
    levels: dict[str, str] = {}
    for dimension in _chapter_list(report, "chapter_5_risk", "dimensions"):
        if not isinstance(dimension, dict):
            continue
        level = str(dimension.get("level") or "").strip().upper()
        match = re.search(r"L[1-4]", level)
        level = match.group(0) if match else level
        for key in (dimension.get("key"), dimension.get("name")):
            if key:
                levels[str(key).strip()] = level
    return levels


def _apply_training_gates(
    report: dict[str, Any],
    sample_quality: dict[str, Any],
    *,
    max_active: int = 2,
) -> None:
    """先决算 Top 1-2 模块，再由 _backfill_dimension_training 回填第三章。"""
    chapter = report.get("chapter_8_training_modules")
    if not isinstance(chapter, dict):
        return
    modules = chapter.get("modules")
    if not isinstance(modules, list) or not modules:
        return

    confidence_rank = {"高": 3.0, "中": 2.0, "低": 1.0}
    dimension_rank: dict[str, float] = {}
    for dimension in _chapter_list(report, "chapter_3_six_dimensions", "dimensions"):
        name = str(dimension.get("name") or "").strip()
        if name:
            dimension_rank[name] = confidence_rank.get(str(dimension.get("confidence") or "").strip(), 1.0)

    levels = _risk_dimension_levels(report)
    risk_rank_by_dimension: dict[str, float] = {}
    for key, name in RISK_DIMENSIONS:
        rank = _RISK_RANK.get(levels.get(key, "") or levels.get(name, ""), 0)
        risk_rank_by_dimension[name] = float(rank)
    has_orange_or_red = any(rank >= 3 for rank in risk_rank_by_dimension.values())

    candidates: list[tuple[float, int, dict[str, Any]]] = []
    expected_dimensions = [name for _, name in SIX_DIMENSIONS]
    for index, module in enumerate(modules):
        if not isinstance(module, dict):
            continue
        normalized_dimensions = [
            matched for value in (module.get("dimensions") or [])
            if (matched := _canonical_dimension_name(value, expected_dimensions))
        ]
        module["dimensions"] = list(dict.fromkeys(normalized_dimensions))
        if not module["dimensions"]:
            continue
        score = max((dimension_rank.get(name, 0.0) for name in module["dimensions"]), default=0.0)
        score += max((risk_rank_by_dimension.get(name, 0.0) for name in module["dimensions"]), default=0.0) * 0.45
        module_name = str(module.get("name") or "")
        if has_orange_or_red and any(keyword in module_name for keyword in ("家庭", "人际", "情绪")):
            score += 0.35
        if not sample_quality.get("low_projection"):
            score += 0.05
        candidates.append((score, index, module))

    if not candidates:
        chapter["active_count"] = 0
        chapter["active_module_ids"] = []
        chapter["active_modules"] = []
        chapter["deferred_modules"] = [str(m.get("name") or "") for m in modules if isinstance(m, dict)]
        return

    ranked = sorted(candidates, key=lambda item: (-item[0], item[1]))
    active_indices = {ranked[0][1]}
    if max_active > 1 and len(ranked) > 1 and ranked[1][0] >= max(2.0, ranked[0][0] - 0.35):
        active_indices.add(ranked[1][1])

    for index, module in enumerate(modules):
        if not isinstance(module, dict):
            continue
        active = index in active_indices
        module["active"] = active
        module["status"] = "优先启动" if active else "暂不启动，待信息补充"

    active_modules = [m for m in modules if isinstance(m, dict) and m.get("active")]
    deferred = [str(module.get("name") or "") for module in modules
                if isinstance(module, dict) and not module.get("active")]
    chapter["active_count"] = len(active_modules)
    chapter["active_module_ids"] = [str(module.get("key") or "") for module in active_modules]
    chapter["active_modules"] = [str(module.get("name") or "") for module in active_modules]
    chapter["deferred_modules"] = deferred
    chapter["decision_basis"] = "先按六维置信度与九维风险紧迫度决算 Top 1-2 模块，再由第三章统一回填启动状态。"
    if max_active <= 1:
        chapter["intensity_note"] = "当前为优先关注/证据有限阶段：暂停高强度训练，本轮仅保留 1 个低强度优先模块。"
        chapter["intro"] = "当前阶段先保留 1 个低强度、低负担的优先模块；其余模块待访谈、量表或更充分沙盘信息后再评估。"
    else:
        chapter["intensity_note"] = ""
        chapter["intro"] = (
            "当前样本投射信息有限，仅启动最相关的 1-2 个模块；其余模块待访谈、量表或更充分沙盘信息后再评估。"
            if sample_quality.get("low_projection")
            else "本次先决算 Top 1-2 个优先模块，其余模块列为次级观察方向，避免同时增加多项训练负担。"
        )


def _backfill_dimension_training(report: dict[str, Any]) -> None:
    """把第八章最终决算结果回填第三章，确保两章模块启停一致。"""
    modules = [
        m for m in _chapter_list(report, "chapter_8_training_modules", "modules")
        if isinstance(m, dict)
    ]
    active_modules = [m for m in modules if m.get("active") is True]
    active_by_dimension: dict[str, list[str]] = {}
    for module in active_modules:
        short = _module_display_name(module.get("name"))
        for dimension_name in module.get("dimensions") or []:
            key = str(dimension_name or "").strip()
            if key:
                active_by_dimension.setdefault(key, [])
                if short not in active_by_dimension[key]:
                    active_by_dimension[key].append(short)

    for dimension in _chapter_list(report, "chapter_3_six_dimensions", "dimensions"):
        if not isinstance(dimension, dict):
            continue
        name = str(dimension.get("name") or "").strip()
        shorts = active_by_dimension.get(name) or []
        if shorts:
            dimension["training_module_directions"] = ["优先启动：" + "、".join(shorts)]
            dimension["training_plan_status"] = "优先启动"
        else:
            dimension["training_module_directions"] = ["列为次级观察方向（本阶段暂不展开）"]
            dimension["training_plan_status"] = "次级观察"


def _cap_low_sample_confidence(report: dict[str, Any], sample_quality: dict[str, Any]) -> None:
    """按样本证据等级限制置信度：低投射量/证据缺失最高为“低”，证据有限最高为“中”。"""
    if sample_quality.get("low_projection") or sample_quality.get("evidence_level") == "minimal":
        cap = "低"
    elif sample_quality.get("evidence_level") == "limited":
        cap = "中"
    else:
        cap = None
    if not cap:
        return
    rank = {"高": 3, "中": 2, "低": 1}
    cap_rank = rank[cap]
    for dimension in _chapter_list(report, "chapter_3_six_dimensions", "dimensions"):
        if not isinstance(dimension, dict):
            continue
        current = str(dimension.get("confidence") or "").strip()
        if rank.get(current, 1) > cap_rank:
            dimension["confidence"] = cap
    for theme in _chapter_list(report, "chapter_2_imagery", "themes"):
        if not isinstance(theme, dict):
            continue
        current = str(theme.get("confidence") or "").strip()
        if rank.get(current, 1) > cap_rank:
            theme["confidence"] = cap
    process = report.get("chapter_3_six_dimensions", {}).get("process_integration")
    if isinstance(process, dict) and process.get("available") is False:
        process["confidence"] = "低"


def _has_interview_material(payload: dict[str, Any], transcript_url: str | None) -> bool:
    """是否有可核对的成绩或访谈类材料。"""
    if transcript_url or str(payload.get("transcript_text") or "").strip():
        return True
    if isinstance(payload.get("transcript"), dict) and payload["transcript"].get("subjects"):
        return True
    if len(str(payload.get("self_narrative") or "").strip()) >= 10:
        return True
    if len(str(payload.get("teacher_observation") or "").strip()) >= 10:
        return True
    return False


def _replace_cognitive_jargon(value: str) -> str:
    return (
        value.replace("认知投注集中在", "注意与情感投入集中在")
        .replace("认知投注", "注意与情感投入")
        .replace("认知资源投注", "注意与情感投入")
    )


def _clean_theory_warning(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"【理论假说·待核实】.*?(?=。|$)", "", text)
    text = re.sub(r"理论假说·待核实[:：]?.*?(?=。|$)", "", text)
    return text.replace("。。", "。").strip()


def _dimension_has_exploration_blocker(dimension: dict[str, Any]) -> bool:
    blob = " ".join(str(dimension.get(field) or "") for field in (
        "judgement", "assessment_result", "conclusion"
    ))
    return any(phrase in blob for phrase in _EXPLORATION_BLOCKERS)


def _sandplay_clues(payload: dict[str, Any]) -> dict[str, Any]:
    items = [item for item in (payload.get("items") or []) if isinstance(item, dict)]
    quality = build_sample_quality(payload)
    occupied = int(quality["occupied_cells"] or 0)
    center_count = int(quality["center_count"] or 0)
    relief = float(quality["heightmap_relief"] or 0.0)
    has_terrain = bool(quality["has_terrain"])

    category_counts: Counter[str] = Counter()
    theme_counts: Counter[str] = Counter()
    labels: list[str] = []
    for item in items:
        label = str(item.get("label") or item.get("name") or "").strip()
        if label:
            labels.append(label)
        category = str(item.get("category") or "").strip()
        if category:
            category_counts[category] += 1
        for theme in item.get("themes") or []:
            if isinstance(theme, str) and theme:
                theme_counts[theme] += 1

    support_labels = [
        label for label in labels
        if any(word in label for word in ("家", "爷爷", "奶奶", "爸爸", "妈妈", "父母", "老师", "朋友", "伙伴"))
    ][:5]
    conflict_labels = [
        label for label in labels
        if any(word in label for word in ("蛇", "狼", "怪兽", "战争", "废墟", "牢", "锁", "墓", "骷髅"))
    ][:5]
    layout_text = (
        f"九宫格占据 {occupied}/9 格、中心区 {center_count} 件、留白 {max(0, 9 - occupied)} 格"
        if occupied else "九宫格空间信息较少，仅能参考沙具分布"
    )
    terrain_text = quality["terrain_summary"]
    return {
        "items_count": len(items),
        "occupied": occupied,
        "center_count": center_count,
        "blank_count": max(0, 9 - occupied),
        "relief": relief,
        "layout_text": layout_text,
        "terrain_text": terrain_text,
        "has_terrain": has_terrain,
        "categories": [name for name, _ in category_counts.most_common(3)],
        "themes": [name for name, _ in theme_counts.most_common(3)],
        "support_labels": support_labels,
        "conflict_labels": conflict_labels,
        "transformation_count": theme_counts.get("transformation", 0),
        "pressure_count": theme_counts.get("pressure", 0) + theme_counts.get("shadow", 0),
        "crisis_count": theme_counts.get("crisis", 0),
    }


def _exploration_text_for_dimension(
    name: str,
    *,
    clues: dict[str, Any],
    payload: dict[str, Any],
) -> tuple[str, str, list[str]]:
    categories = "、".join(clues["categories"]) or "尚未形成明显类别"
    themes = "、".join(clues["themes"]) or "主题标签较少"
    representative = str(payload.get("representative_item_name") or "").strip()
    narrative = str(payload.get("self_narrative") or "").strip()
    teacher = str(payload.get("teacher_observation") or "").strip()
    layout = clues["layout_text"]
    terrain = clues["terrain_text"]
    if name == "全学科认知诊断":
        judgement = (
            f"从沙盘空间看，{layout}，{terrain}；主要意象为{categories}。"
            "这些线索可用于观察注意资源分配、任务组织与持续投入方式，但不能直接替代学科能力判断。"
        )
        terrain_clue = (
            "地形塑形为计划性、步骤组织和元认知监控提供探索线索"
            if clues.get("has_terrain")
            else "当前沙面基本平整，地形线索不足以支持计划性判断"
        )
        pressure_clue = (
            f"压力与阴影主题共 {clues['pressure_count']} 件，提示情绪负荷可能占用专注带宽"
            if clues["pressure_count"]
            else "本次未识别压力/阴影主题标签，不能据此判断情绪负荷高低"
        )
        result = (
            f"{pressure_clue}；{layout}，{terrain_clue}。"
            "在无成绩单时，这些只能作为学习过程的假设，需结合课堂任务表现核验。"
        )
    elif name == "文理选科适配":
        judgement = (
            f"沙盘以{categories}为主要意象，空间布局为{layout}。"
            "这可作为任务偏好（偏结构、偏叙事或偏关系）的探索线索，不足以直接形成文理强弱对照。"
        )
        result = (
            f"代表沙具「{representative or '未指定'}」与{themes}主题共同出现，"
            "提示可观察受测者在结构化任务与开放表达任务中的投入差异；选科适配仍需成绩、学科自述和教师观察三方核验。"
        )
    elif name == "兴趣特长与潜能":
        judgement = (
            f"反复出现的{categories}与{themes}主题，提供了兴趣入口的探索方向；"
            "沙盘中的主动选择不等同于稳定特长。"
        )
        result = (
            f"代表沙具「{representative or '未指定'}」可作为访谈切入口，"
            f"{'自述中已出现相关表达，' if narrative else ''}"
            "需在真实任务、社团或项目体验中检验兴趣的持续性与胜任感。"
        )
    elif name == "升学与学业规划":
        judgement = (
            f"空间呈现为{layout}，{terrain}；可据此观察受测者对步骤、边界和优先级的组织方式。"
            "该线索只用于提出学习规划假设。"
        )
        result = (
            f"中心区 {clues['center_count']} 件、留白 {clues['blank_count']} 格，"
            "可分别理解为目标聚焦与尚未纳入规划的区域；升学规划需结合近期成绩趋势、时间管理与家庭安排核实。"
        )
    elif name == "家庭生态协同":
        support = "、".join(clues["support_labels"]) or "暂未识别明确的家庭/支持意象"
        conflict = "、".join(clues["conflict_labels"]) or "暂未识别明显的冲突意象"
        judgement = (
            f"沙盘中家庭与支持类意象包括：{support}；冲突/威胁类意象包括：{conflict}。"
            "这些内容提示家庭支持与张力的可能来源，需访谈核实。"
        )
        result = (
            f"{'受测者自述或教师观察提到家庭相关情境；' if ('家' in narrative + teacher) else ''}"
            "家庭协同的方向应优先了解支持资源、沟通规则与学业期待，而不是仅凭沙具位置下结论。"
        )
    else:
        judgement = (
            f"沙盘整体为{layout}，{terrain}；{themes}主题与{categories}构成主要动力线索。"
            "转化类意象与中心聚集可作为动力恢复的探索性指标。"
        )
        result = (
            f"转化主题 {clues['transformation_count']} 件、危机主题 {clues['crisis_count']} 件；"
            f"{'自述中出现压力或坚持相关表达，' if narrative else ''}"
            "提示动力源可能来自关系支持、掌控体验或阶段性目标，需在访谈中确认。"
        )
    evidence = [
        layout,
        terrain,
        f"主要类别：{categories}",
        f"主要主题：{themes}",
    ]
    if representative:
        evidence.append(f"代表沙具：{representative}")
    if narrative:
        evidence.append(f"受测者自述：{narrative[:40]}")
    if teacher:
        evidence.append(f"教师观察：{teacher[:40]}")
    return judgement, result, evidence


def _ensure_six_dimension_exploration(
    report: dict[str, Any],
    payload: dict[str, Any],
    transcript_url: str | None,
) -> None:
    """无成绩/无访谈时仍输出六维探索性推理，不允许硬拦截。"""
    clues = _sandplay_clues(payload)
    has_material = _has_interview_material(payload, transcript_url)
    has_scores = any(
        isinstance(row, dict) and row.get("score") is not None
        for row in _chapter_list(report, "chapter_4_academic", "subjects")
    )
    for dimension in _chapter_list(report, "chapter_3_six_dimensions", "dimensions"):
        if not isinstance(dimension, dict):
            continue
        name = str(dimension.get("name") or "").strip()
        blocked = _dimension_has_exploration_blocker(dimension)
        if blocked:
            judgement, result, evidence = _exploration_text_for_dimension(
                name, clues=clues, payload=payload
            )
            dimension["judgement"] = judgement
            dimension["assessment_result"] = result
            dimension["evidence"] = evidence

        evidence_list = dimension.get("evidence")
        if not isinstance(evidence_list, list) or not evidence_list:
            dimension["evidence"] = [
                clues["layout_text"],
                clues["terrain_text"],
                f"主要类别：{'、'.join(clues['categories']) or '未分类'}",
            ]
        else:
            dimension["evidence"] = [
                _replace_cognitive_jargon(_clean_theory_warning(item))
                if isinstance(item, str) else item
                for item in evidence_list
            ]
        for field in ("judgement", "assessment_result"):
            if isinstance(dimension.get(field), str):
                dimension[field] = _replace_cognitive_jargon(
                    _clean_theory_warning(dimension[field])
                )

        conclusion = _dedupe_exploration_disclaimer(
            _clean_theory_warning(dimension.get("conclusion"))
        )
        if not _has_exploration_disclaimer(conclusion):
            conclusion = (conclusion.rstrip("。") + "。" if conclusion else "") + _EXPLORATION_DISCLAIMER
        elif conclusion and conclusion[-1] not in "。！？":
            conclusion += "。"
        dimension["conclusion"] = conclusion

        confidence = str(dimension.get("confidence") or "").strip()
        if not has_material and confidence == "高":
            dimension["confidence"] = "中"
        if (not has_material) and (not has_scores) and clues["items_count"] < 3:
            dimension["confidence"] = "低"


def _apply_theory_guardrails(
    report: dict[str, Any],
    payload: dict[str, Any],
    transcript_url: str | None,
) -> None:
    """为六维绑定干净理论，清除补丁式重复警告。"""
    _ensure_six_dimension_exploration(report, payload, transcript_url)
    for dimension in _chapter_list(report, "chapter_3_six_dimensions", "dimensions"):
        if not isinstance(dimension, dict):
            continue
        name = str(dimension.get("name") or "").strip()
        canonical = SIX_DIMENSION_THEORIES.get(name)
        if canonical:
            dimension["assessment_theory"] = canonical
        else:
            dimension["assessment_theory"] = _clean_theory_warning(dimension.get("assessment_theory"))

    chapter_7 = report.get("chapter_7_career")
    if isinstance(chapter_7, dict):
        if not chapter_7.get("evidence_note"):
            chapter_7["evidence_note"] = (
                "以下优势为基于当前沙盘、自述与教师观察的探索性假设，不等同于能力测评或稳定人格结论；"
                "每条优势都需回到具体行为线索，并结合访谈、教师或家长观察核实。"
            )
        replacements = {
            "具备良好的情感感知能力，能够敏锐捕捉到身边人的情绪变化": "愿意关注家人感受；对他人情绪的敏感度需结合日常观察核实",
            "具备良好的人际互动基础": "人际互动基础需进一步观察",
            "心理韧性基础较好": "韧性水平需结合情境评估",
        }
        strengths = chapter_7.get("strengths")
        if isinstance(strengths, list):
            softened: list[Any] = []
            for strength in strengths:
                value = str(strength)
                for old, new in replacements.items():
                    value = value.replace(old, new)
                softened.append(value)
            chapter_7["strengths"] = softened


def _soften_self_harm_l1(text: str) -> str:
    """L1 的自我伤害维度只做常规访谈观察，不使用高危核查措辞。"""
    value = str(text or "")
    replacements = (
        ("C-SSRS（哥伦比亚自杀严重程度评定量表）", "常规情绪与安全感访谈观察"),
        ("C-SSRS", "常规情绪与安全感访谈观察"),
        ("必须由专业人员面对面安全核查", "建议在常规情绪与安全感访谈中持续观察"),
        ("必须面对面安全核查", "建议在常规情绪与安全感访谈中持续观察"),
        ("需由专业人员后续面对面安全核查确认", "建议在常规情绪与安全感访谈中持续观察"),
        ("需由专业人员后续面对面完成安全核查", "建议在常规情绪与安全感访谈中持续观察"),
        ("需由专业人员面对面完成安全核查", "建议在常规情绪与安全感访谈中持续观察"),
        ("需由专业人员面对面开展安全核查", "建议在常规情绪与安全感访谈中持续观察"),
        ("需由专业人员面对面安全核查", "建议在常规情绪与安全感访谈中持续观察"),
        ("由专业人员面对面完成安全核查", "建议在常规情绪与安全感访谈中持续观察"),
        ("由专业人员面对面开展安全核查", "建议在常规情绪与安全感访谈中持续观察"),
        ("由专业人员面对面安全核查", "建议在常规情绪与安全感访谈中持续观察"),
        ("必须立即进行安全核查", "建议结合常规访谈持续观察，若情绪恶化再启用 C-SSRS 筛查"),
        ("需立即进行安全核查", "建议结合常规访谈持续观察，若情绪恶化再启用 C-SSRS 筛查"),
        ("必须进行安全核查", "建议结合常规访谈持续观察"),
        ("建议立即转介", "建议结合常规访谈持续观察，必要时再转介"),
    )
    for old, new in replacements:
        value = value.replace(old, new)
    value = re.sub(
        r"(?:必须|需要|需|应)?(?:由)?专业人员(?:后续)?面对面(?:完成|开展)?安全核查(?:确认)?",
        "建议在常规情绪与安全感访谈中持续观察",
        value,
    )
    return value


def _ensure_chapter9(report: dict[str, Any]) -> None:
    """兜底第九章三段建议，避免字段为空导致小标题在打印时丢失。"""
    chapter = report.get("chapter_9_general_advice")
    if not isinstance(chapter, dict):
        chapter = {}
        report["chapter_9_general_advice"] = chapter
    chapter.setdefault("title", "总体使用建议")
    fallbacks = {
        "growth_mindset": "把当前困难视为可通过练习、支持与时间逐步改善的阶段性问题，避免用一次表现给自己或受测者下固定结论。",
        "strength_transfer": "把沙盘中已经出现的边界感、秩序感或情绪觉察线索，迁移到日常学习与家庭沟通中，并在真实情境中继续观察。",
        "capability_not_label": "报告中的描述指向当前阶段的能力表现与支持需求，不作为稳定人格、能力高低或诊断标签使用。",
    }
    for key, fallback in fallbacks.items():
        value = chapter.get(key)
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            value = []
        value = [str(item).strip() for item in value if str(item or "").strip()]
        chapter[key] = value or [fallback]
    chapter.setdefault(
        "disclaimer",
        "本报告为发展性心理评估参考，非临床诊断；所有假设以访谈与专业判断为准。",
    )


def _apply_risk_guardrails(report: dict[str, Any], sample_quality: dict[str, Any]) -> None:
    chapter = report.get("chapter_5_risk")
    if not isinstance(chapter, dict):
        return
    base_disclaimer = "仅供咨询师在专业范围内审阅，不可直接呈现给受测者及其家属；不替代量表、访谈和转介。"
    current = str(chapter.get("disclaimer") or "").strip()
    chapter["disclaimer"] = current if "未见负向沙具" in current else (
        (current + " " if current else base_disclaimer + " ")
        + "低投射量样本中“未见负向沙具”不等于无风险，需结合访谈与相应量表核实。"
    )

    for dimension in _chapter_list(report, "chapter_5_risk", "dimensions"):
        if not isinstance(dimension, dict):
            continue
        key = str(dimension.get("key") or "").strip()
        name = str(dimension.get("name") or "").strip()
        instrument = RISK_INSTRUMENTS.get(key)
        if not instrument:
            for risk_key, risk_name in RISK_DIMENSIONS:
                if name == risk_name:
                    instrument = RISK_INSTRUMENTS.get(risk_key)
                    break
        if instrument:
            dimension["norm_reference"] = instrument
        elif not str(dimension.get("norm_reference") or "").strip():
            dimension["norm_reference"] = "需由专业人员根据该维度选择对应量表与访谈核实"
        level_match = re.search(r"L[1-4]", str(dimension.get("level") or "").upper())
        level = level_match.group(0) if level_match else ""
        is_self_harm = key == "self_harm" or name == "自我伤害倾向"
        if is_self_harm and level == "L1":
            dimension["norm_reference"] = (
                "常规情绪与安全感访谈观察（若后续出现情绪恶化再启用 C-SSRS 筛查）"
            )
            for field in ("judgement", "assessment_result", "conclusion", "suggestion"):
                if str(dimension.get(field) or "").strip():
                    dimension[field] = _soften_self_harm_l1(dimension.get(field))
        elif is_self_harm:
            dimension["norm_reference"] = RISK_INSTRUMENTS.get("self_harm", dimension.get("norm_reference"))
        if level == "L1" and "未见显性" not in str(dimension.get("judgement") or ""):
            judgement = str(dimension.get("judgement") or "").strip().rstrip("。")
            dimension["judgement"] = (
                (judgement + "；" if judgement else "")
                + "该结论仅基于当前沙盘，未见显性线索不等于无风险，需结合访谈/量表核实。"
            )


_RISK_LABELS = {
    "L1": "L1 平稳",
    "L2": "L2 轻度关注",
    "L3": "L3 中度关注",
    "L4": "L4 高度关注",
}


def _risk_label(level: str) -> str:
    return _RISK_LABELS.get(level, level)


def _set_risk_dimension_floor(
    report: dict[str, Any],
    key: str,
    level: str,
    *,
    judgement: str = "",
    evidence: str = "",
) -> None:
    for dimension in _chapter_list(report, "chapter_5_risk", "dimensions"):
        if not isinstance(dimension, dict):
            continue
        if str(dimension.get("key") or "").strip() != key:
            continue
        current = str(dimension.get("level") or "").strip().upper()
        if _RISK_RANK.get(current, 0) >= _RISK_RANK.get(level, 0):
            return
        dimension["level"] = level
        dimension["label"] = _risk_label(level)
        if judgement:
            dimension["judgement"] = judgement
        if evidence:
            existing = str(dimension.get("evidence") or "").strip().rstrip("。；; ")
            dimension["evidence"] = f"{existing}；{evidence}" if existing else evidence
        if key == "self_harm":
            dimension["norm_reference"] = RISK_INSTRUMENTS.get("self_harm", dimension.get("norm_reference"))
        return


def _apply_risk_consistency(report: dict[str, Any], priority_level: str) -> None:
    """让顶部预警、第五章总体等级与风险表不再互相矛盾。"""
    chapter = report.get("chapter_5_risk")
    if not isinstance(chapter, dict):
        return
    banner = report.get("priority_banner") if isinstance(report.get("priority_banner"), dict) else {}
    banner_level = str(banner.get("level") or priority_level or "").strip().upper()
    banner_match = re.search(r"L[1-4]", banner_level)
    banner_rank_level = banner_match.group(0) if banner_match else banner_level
    triggers = [str(item) for item in (banner.get("triggers") or []) if str(item).strip()]
    levels = _risk_dimension_levels(report)
    max_dimension_level = max((_RISK_RANK.get(level, 0) for level in levels.values()), default=0)
    banner_rank = _RISK_RANK.get(banner_rank_level, 0)

    if banner_rank >= 4:
        trigger_blob = " ".join(triggers)
        holistic_trigger = any(str(item).startswith("整体构图") for item in triggers)
        if holistic_trigger:
            note = (
                "本次沙盘整体构图形成明确的高危文字/符号，属于重大风险线索；"
                "其优先级高于单个沙具的常规含义，需立即核查死亡、自伤与危机相关表达，"
                "并完成 24 小时安全核查与专业转介评估。"
            )
            self_harm_floor = "L4"
        elif any(word in trigger_blob for word in ("自伤", "绝望", "不想活", "活着没意思", "自杀")):
            note = "本次出现 L4 自伤/绝望文本触发线索，需优先核查自伤与死亡相关表达；该分级来自触发线索，需访谈与 C-SSRS 核实。"
            self_harm_floor = "L3"
        else:
            note = "本次出现 L4 高危画面触发线索，需优先核查死亡、自伤与危机相关表达；该分级来自触发线索，需访谈与 C-SSRS 核实。"
            self_harm_floor = "L3"
        _set_risk_dimension_floor(
            report,
            "self_harm",
            self_harm_floor,
            judgement=note,
            evidence="；".join(triggers[:4]) or "L4 优先级触发",
        )
        max_dimension_level = max(
            max((_RISK_RANK.get(level, 0) for level in _risk_dimension_levels(report).values()), default=0),
            max_dimension_level,
        )

    overall_rank = max(banner_rank, max_dimension_level)
    overall_level = next((level for level, rank in _RISK_RANK.items() if rank == overall_rank), "")
    if overall_level:
        chapter["overall_level"] = overall_level
        chapter["overall_label"] = _risk_label(overall_level)
    if banner_rank:
        chapter["priority_override"] = {
            "level": banner_level,
            "triggers": triggers[:8],
            "message": "顶部预警由文本/高危画面/过程线索触发，优先级高于九维模型分级；风险表需结合访谈与量表人工核对。",
        }
    if banner_rank > max_dimension_level:
        chapter["consistency_warning"] = (
            f"顶部预警来自文本/沙具/过程线索（{banner_level}），九维风险表为模型分级，最高为 "
            f"{_risk_label(next((level for level, rank in _RISK_RANK.items() if rank == max_dimension_level), 'L1'))}；"
            "已标注优先级覆盖，需人工核对，不能把风险表低等级理解为“无风险”。"
        )


def _career_text_has_score_claim(text: str) -> bool:
    value = str(text or "")
    value = re.sub(r"(暂不|不|未)(结合|以|使用|提供|依赖)成绩", "", value)
    value = re.sub(r"(没有|无|缺少)成绩", "", value)
    return any(word in value for word in ("可读成绩", "成绩中", "成绩基础", "结合成绩"))


def _rewrite_career_for_evidence(
    report: dict[str, Any],
    sample_quality: dict[str, Any],
    priority_level: str,
) -> None:
    """低投射量/证据有限或缺失时暂停职业定位；没有成绩时删除“可读成绩”类表述。"""
    chapter = report.get("chapter_7_career")
    if not isinstance(chapter, dict):
        return
    chapter4 = report.get("chapter_4_academic") if isinstance(report.get("chapter_4_academic"), dict) else {}
    has_scores = bool(sample_quality.get("has_scores")) or any(
        isinstance(row, dict) and row.get("score") is not None
        for row in (chapter4.get("subjects") or [])
    )
    low_evidence = (
        bool(sample_quality.get("low_projection"))
        or sample_quality.get("evidence_level") in ("minimal", "limited")
    )
    text_fields = ("summary", "evidence_note", "career_resume_note")
    if not has_scores:
        for field in text_fields:
            value = str(chapter.get(field) or "")
            if _career_text_has_score_claim(value):
                value = (
                    value.replace("结合可读成绩探索优势方向", "暂不结合成绩排序，先探索兴趣与任务投入")
                    .replace("在可读成绩中显示出相对稳定的记忆/理解类学习基础", "在访谈与任务表现中继续观察学习基础")
                    .replace("可读成绩", "现有文本线索")
                    .replace("结合成绩", "结合后续成绩")
                )
                chapter[field] = value
        strengths = chapter.get("strengths")
        if isinstance(strengths, list):
            chapter["strengths"] = [
                str(item) for item in strengths
                if not _career_text_has_score_claim(str(item))
            ] or ["当前未提供成绩数据，暂不以成绩推断优势；建议先补充访谈与任务表现。"]
    if priority_level in ("L3_ORANGE", "L4_RED"):
        return
    if not low_evidence:
        return

    strengths = chapter.get("strengths")
    filtered: list[str] = []
    if isinstance(strengths, list):
        for item in strengths:
            text = str(item)
            if _career_text_has_score_claim(text) and not has_scores:
                continue
            if "愿意通过沙盘表达" in text and not sample_quality.get("has_narrative"):
                continue
            if any(word in text for word in ("投入明显", "空间组织感")) and int(sample_quality.get("item_count") or 0) < 3:
                continue
            if not any(marker in text for marker in ("代表沙具", "沙盘布局中", "自述", "教师观察")):
                continue
            filtered.append(text)
    if not filtered:
        filtered = [
            f"当前仅有 {int(sample_quality.get('item_count') or 0)} 件沙具，尚不足以形成稳定的兴趣或优势判断；"
            "建议在访谈中补充选择理由、任务坚持性与真实项目体验。"
        ]
    chapter.update({
        "title": PROTECTIVE_CHAPTER_TITLE,
        "stage": "证据补充与资源观察优先",
        "career_postponed": True,
        "summary": (
            "当前沙具/文本证据有限，暂缓具体职业定位与优势排序；先呈现可观察的兴趣与资源线索，"
            "待补充访谈、教师观察或成绩后再评估。"
        ),
        "strengths": filtered,
        "career_resume_note": "待补充自述、教师观察、成绩或过程数据后，再评估职业发展方向。",
    })
    chapter["evidence_note"] = (
        "以上仅为当前沙盘与有限文本中的探索性观察，不等同于能力测评或稳定人格结论；"
        "低投射量/证据缺失阶段不做职业优势排序。"
    )


def _priority_text_blob(payload: dict[str, Any]) -> str:
    return "\n".join(str(payload.get(field) or "") for field in (
        "sandplay_description", "self_narrative", "teacher_observation", "transcript_text"
    ))


def _merge_holistic_screen(report: dict[str, Any], screen: dict[str, Any] | None) -> dict[str, Any]:
    """把独立整体构图筛查结果写入第一章；模型漏写时由服务端补位。"""
    chapter_1 = report.get("chapter_1_overview")
    if not isinstance(chapter_1, dict):
        return {}
    existing = chapter_1.get("holistic_visual_check")
    merged = dict(existing) if isinstance(existing, dict) else {}
    if isinstance(screen, dict) and screen.get("status") == "ok":
        for key in ("overall_forms", "readable_text"):
            value = screen.get(key)
            if isinstance(value, list) and value:
                merged[key] = value
        for key in ("symbol_meaning", "risk_evidence"):
            value = str(screen.get(key) or "").strip()
            if value:
                previous = str(merged.get(key) or "").strip().rstrip("。；; ")
                if previous:
                    previous_norm = re.sub(r"[\s，。；、：“”\"']", "", previous)
                    value_norm = re.sub(r"[\s，。；、：“”\"']", "", value)
                    if previous_norm and (previous_norm in value_norm or value_norm in previous_norm):
                        merged[key] = previous if len(previous) >= len(value) else value
                    else:
                        merged[key] = f"{previous}；{value}"
                else:
                    merged[key] = value
        screen_level = str(screen.get("risk_level") or "").strip().lower()
        if screen_level == "high" or is_high_risk(screen):
            merged["risk_level"] = "high"
        elif not str(merged.get("risk_level") or "").strip():
            merged["risk_level"] = screen_level or "none"
        visual_objects = [
            item for item in (screen.get("visual_risk_objects") or [])
            if isinstance(item, dict)
        ]
        if visual_objects:
            existing_objects = [
                item for item in (merged.get("visual_risk_objects") or [])
                if isinstance(item, dict)
            ]
            merged["visual_risk_objects"] = visual_objects + existing_objects
            deduped = []
            seen = set()
            for item in merged["visual_risk_objects"]:
                key = (
                    str(item.get("type") or ""),
                    str(item.get("label") or ""),
                    str(item.get("severity") or ""),
                )
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(item)
            merged["visual_risk_objects"] = deduped[:12]
            visual_level = str(screen.get("visual_risk_level") or "").strip().lower()
            if visual_level not in {"high", "watch", "none"}:
                visual_level = "watch" if any(
                    str(item.get("severity") or "").lower() == "watch" for item in visual_objects
                ) else "none"
            merged["visual_risk_level"] = visual_level
            if not str(merged.get("visual_risk_summary") or "").strip():
                merged["visual_risk_summary"] = str(screen.get("visual_risk_summary") or "").strip()
        if not str(merged.get("confidence") or "").strip():
            merged["confidence"] = str(screen.get("confidence") or "unknown")
    if isinstance(screen, dict):
        merged["screen_status"] = str(screen.get("status") or "unknown")
    if merged:
        chapter_1["holistic_visual_check"] = merged
    return merged


def _holistic_priority(report: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
    chapter_1 = report.get("chapter_1_overview") if isinstance(report.get("chapter_1_overview"), dict) else {}
    check = chapter_1.get("holistic_visual_check") if isinstance(chapter_1.get("holistic_visual_check"), dict) else {}
    screen = payload.get("_holistic_screen") if isinstance(payload.get("_holistic_screen"), dict) else {}

    triggers: list[str] = []
    if is_high_risk(check):
        triggers.extend(screen_triggers(check))
    if is_high_risk(screen):
        triggers.extend(screen_triggers(screen))
    triggers = list(dict.fromkeys(item for item in triggers if item))
    if triggers:
        return {"level": "L4_RED", "triggers": triggers}

    if screen.get("status") == "failed":
        return {
            "level": "L3_ORANGE",
            "triggers": ["整体构图安全筛查未完成：需人工复核整体画面"],
        }
    return None


def _visual_priority(
    report: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    """视觉高危物体的分级：单件非死亡物 L3；尸体/悬吊/多件 high L4。"""
    screen = payload.get("_holistic_screen") if isinstance(payload.get("_holistic_screen"), dict) else {}
    chapter_1 = report.get("chapter_1_overview") if isinstance(report.get("chapter_1_overview"), dict) else {}
    check = chapter_1.get("holistic_visual_check") if isinstance(chapter_1.get("holistic_visual_check"), dict) else {}
    objects: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for source in (screen, check):
        for item in (source.get("visual_risk_objects") or []):
            if not isinstance(item, dict):
                continue
            key = (
                str(item.get("type") or ""),
                str(item.get("label") or ""),
                str(item.get("severity") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            objects.append(item)

    high = [item for item in objects if str(item.get("severity") or "").lower() == "high"]
    death = [
        item for item in high
        if str(item.get("type") or "") in {"corpse", "hanging"}
        or any(word in str(item.get("label") or "") for word in ("尸体", "遗体", "上吊", "悬吊"))
    ]
    l4_triggers: list[str] = []
    l3_triggers: list[str] = []
    if death:
        l4_triggers.extend(visual_risk_triggers({"visual_risk_objects": death}))
        l4_triggers.append("视觉死亡符号：需立即进行安全核查")
    if len(high) >= 2:
        l4_triggers.append(f"视觉高危物体 {len(high)} 件：需按重大风险人工复核")
    elif high and not death:
        l3_triggers.extend(visual_risk_triggers({"visual_risk_objects": high}))
        l3_triggers.append("单件视觉高危物体：降为 L3 人工复核，需核实朝向、人物关系与场景语境")
    if not high and str(screen.get("visual_risk_level") or "").lower() == "high":
        l3_triggers.append("视觉筛查提示高危但未返回结构化物体：需人工复核原图")
    if l4_triggers:
        return {"level": "L4_RED", "triggers": list(dict.fromkeys(l4_triggers))}
    if l3_triggers:
        return {"level": "L3_ORANGE", "triggers": list(dict.fromkeys(l3_triggers))}
    return None


def _detect_priority(
    report: dict[str, Any],
    payload: dict[str, Any],
    transcript_url: str | None,
) -> dict[str, Any] | None:
    l4_triggers: list[str] = []
    l3_triggers: list[str] = []
    text_blob = _priority_text_blob(payload)

    holistic = _holistic_priority(report, payload)
    if holistic:
        target = l4_triggers if holistic["level"] == "L4_RED" else l3_triggers
        target.extend(holistic.get("triggers") or [])

    visual = _visual_priority(report, payload)
    if visual:
        target = l4_triggers if visual["level"] == "L4_RED" else l3_triggers
        target.extend(visual.get("triggers") or [])

    high_risk_items = [
        item for item in (payload.get("items") or [])
        if isinstance(item, dict) and str(item.get("risk_tier") or "").lower() == "high_risk"
    ]
    high_risk_labels = [
        str(item.get("label") or item.get("name") or "高危沙具").strip()
        for item in high_risk_items
    ]
    severe_names = [
        label for label in high_risk_labels
        if any(word in label for word in _DEATH_ITEM_WORDS)
    ]
    if severe_names:
        l4_triggers.extend(f"高危画面：{name}" for name in severe_names[:4])
    if len(high_risk_items) >= 2:
        l4_triggers.append(f"多件高危沙具：{len(high_risk_items)} 件，需按重大风险人工复核")
    elif high_risk_items and not severe_names:
        l3_triggers.append(
            f"单件高危沙具：{high_risk_labels[0]}；降为 L3 人工复核，需结合场景语境、位置与过程证据"
        )

    for match in _L4_TEXT_RE.finditer(text_blob):
        l4_triggers.append(f"自伤/绝望文本：{match.group(1)}")
    for word in _DEATH_ITEM_WORDS:
        if word in text_blob:
            l4_triggers.append(f"死亡/高危关键词：{word}")
    for word in _HIGH_RISK_ITEM_WORDS:
        if word in text_blob and word not in _DEATH_ITEM_WORDS:
            l3_triggers.append(f"高危沙具关键词：{word}")

    for match in _DESTRUCTION_TEXT_RE.finditer(text_blob):
        l4_triggers.append(f"掩埋/破坏操作描述：{match.group(1)}")

    telemetry = _process_telemetry(payload)
    if telemetry["bury_actions"]:
        l4_triggers.append(f"制作过程：掩埋人物 {len(telemetry['bury_actions'])} 次")
    if telemetry["destructive_loops"]:
        l4_triggers.append(f"制作过程：短时反复放删 {telemetry['destructive_loops']} 次")

    interaction = payload.get("interaction_summary") or {}
    for key in ("buried_count", "destroyed_count", "delete_count", "removed_count"):
        value = interaction.get(key)
        if isinstance(value, (int, float)) and value >= 1:
            l4_triggers.append(f"操作记录：{key}={int(value)}")

    levels = _risk_dimension_levels(report)
    expected = dict(RISK_DIMENSIONS)
    l4_dimensions = [
        expected.get(key, key) for key, level in levels.items()
        if level == "L4"
    ]
    if l4_dimensions:
        l4_triggers.extend(f"九维风险达 L4：{name}" for name in l4_dimensions)

    l3_dimensions = [
        expected.get(key, key) for key, level in levels.items()
        if level == "L3"
    ]
    if l3_dimensions:
        l3_triggers.extend(f"九维风险达 L3：{name}" for name in l3_dimensions)
    for match in _L3_TEXT_RE.finditer(text_blob):
        l3_triggers.append(f"自述/教师观察关键词：{match.group(1)}")

    l4_triggers = list(dict.fromkeys(item for item in l4_triggers if item))
    l3_triggers = list(dict.fromkeys(item for item in l3_triggers if item))
    if l4_triggers:
        return {"level": "L4_RED", "triggers": l4_triggers}
    if l3_triggers:
        return {"level": "L3_ORANGE", "triggers": l3_triggers}
    return None


def _protective_chapter_content(
    report: dict[str, Any],
    payload: dict[str, Any],
    level: str,
) -> dict[str, Any]:
    clues = _sandplay_clues(payload)
    strengths: list[str] = []
    if clues["transformation_count"]:
        strengths.append(
            f"沙盘中已出现 {clues['transformation_count']} 件转化/修复主题意象，可作为受测者仍在寻求修复与出路的观察线索。"
        )
    if clues["support_labels"]:
        strengths.append(
            f"沙盘中存在可识别的支持性意象：{'、'.join(clues['support_labels'])}，提示关系资源可作为渡过难关的支点。"
        )
    if clues["center_count"]:
        strengths.append(
            f"中心区聚集 {clues['center_count']} 件，提示受测者仍有自我掌控与组织经验，可被后续任务激活。"
        )
    if str(payload.get("self_narrative") or "").strip() or str(payload.get("teacher_observation") or "").strip():
        strengths.append("受测者愿意留下自述或教师已提供观察，说明当前仍存在可继续沟通与建立联盟的通道。")
    if not strengths:
        strengths.append("当前沙盘与文本线索有限，但受测者完成作品本身即为一次可被承接的表达，需在访谈中寻找其可用的支持资源。")

    if level == "L4_RED":
        summary = (
            "当前阶段暂停具体职业定位与优势排序，优先呈现受测者可用于渡过难关的内在心理资源与外部保护因素。"
            "以下内容仅用于支持安全稳定，不替代危机干预。"
        )
        teacher_actions = [
            "24 小时内完成一次私下、无评判的安全核查，直接询问受测者当前是否有自伤或结束生命的想法、计划与可接触工具。",
            "立即通知学校危机干预负责人与监护人，明确专人陪护与交接安排，不让受测者独处。",
            "暂时降低公开评价、排名与学业施压，优先恢复作息、睡眠与基本安全感。",
            "记录高危画面、掩埋/破坏操作与自伤绝望文本的原话，按危机流程转介专业机构。",
        ]
        parent_actions = [
            "尽快到校与班主任、心理老师面对面沟通，如实告知近期情绪与生活事件。",
            "移除家中可被用于自伤的工具与药品，安排连续陪伴与夜间观察。",
            "避免追问成绩、指责或说教，先用“受测者现在是否安全、是否需要陪伴”建立连接。",
            "按专业建议尽快就医或联系危机干预资源，不把沙盘报告当作诊断结论。",
        ]
        student_actions = [
            "受测者可先联系一位可信任的成年人陪伴，不独自处理强烈情绪。",
            "若出现自伤冲动，受测者应立即离开危险物品并前往有人陪伴的空间。",
            "受测者可用简单方式表达“现在需要有人陪着”，不必先解释清楚全部原因。",
        ]
    else:
        summary = (
            "当前阶段暂缓具体职业定位，优先确认校园安全、情绪稳定与支持网络。"
            "以下保护性因素用于帮助受测者恢复稳定，而不是对其能力下结论。"
        )
        teacher_actions = [
            "优先开展校园安全与情绪稳定访谈，了解是否存在霸凌、欺凌、威胁、勒索或重大变故。",
            "确认受测者在班级中的座位、同伴关系、上下学路线与可信任成人，必要时启动校园安全保护流程。",
            "与家长沟通时先描述观察到的情绪与行为变化，不贴标签、不公开比较。",
            "若受测者拒绝交流，改用书面、第三人转述或共同活动等低压力方式建立接触。",
        ]
        parent_actions = [
            "先倾听受测者对学校人际与家庭事件的描述，不急于追问成绩或要求立刻振作。",
            "与学校确认是否存在霸凌、欺凌或重大变故，并约定固定的沟通与保护安排。",
            "保持作息、饮食与陪伴的稳定，减少重大变动叠加。",
        ]
        student_actions = [
            "受测者可先向班主任、心理老师或可信任同伴说明当前最困扰的一件事。",
            "受测者可在感到不安全时前往办公室、心理室等明确的安全地点。",
            "受测者不必独自承受全部压力，可先选择一个可信任的成年人保持联系。",
        ]

    chapter_7 = report.get("chapter_7_career")
    if not isinstance(chapter_7, dict):
        chapter_7 = {}
        report["chapter_7_career"] = chapter_7
    chapter_7.update({
        "title": PROTECTIVE_CHAPTER_TITLE,
        "stage": "安全稳定与保护性因素优先",
        "career_postponed": True,
        "summary": summary,
        "evidence_note": "以上保护性因素来自沙盘意象、受测者自述与教师观察，需在访谈中逐条核实，不作能力或人格定论。",
        "strengths": strengths,
        "teacher_actions": teacher_actions,
        "parent_actions": parent_actions,
        "student_actions": student_actions,
        "career_resume_note": "待校园安全、情绪稳定与支持网络确认后，再评估职业发展方向。",
    })
    return chapter_7


def _apply_priority_routing(
    report: dict[str, Any],
    payload: dict[str, Any],
    transcript_url: str | None,
) -> str:
    priority = _detect_priority(report, payload, transcript_url)
    if not priority:
        report.pop("priority_banner", None)
        chapter_7 = report.get("chapter_7_career")
        if isinstance(chapter_7, dict) and "chapter_7_career" in CHAPTER_TITLES:
            chapter_7["title"] = CHAPTER_TITLES["chapter_7_career"]
            chapter_7["career_postponed"] = False
        return "normal"

    level = priority["level"]
    triggers = priority["triggers"]
    if level == "L4_RED":
        banner = {
            "level": "L4_RED",
            "severity": 4,
            "visibility": "counselor_only",
            "title": "L4 红色预警：24 小时内完成危机安全核查",
            "message": "检测到高危画面、掩埋/破坏操作或自伤绝望文本，优先保障受测者人身安全，暂停常规训练与职业定位。",
            "triggers": triggers[:8],
            "recommended_actions": [
                "24 小时内由学校心理老师、班主任与监护人共同完成面对面安全核查。",
                "直接询问自伤念头、计划、可接触工具与既往尝试，不回避、不评判。",
                "安排专人陪护与交接，移除可接触的危险物品，必要时立即转介医疗机构。",
                "暂停第八章训练模块与职业定位，待危机稳定后再恢复发展性评估。",
            ],
            "checklist_24h": [
                "确认受测者当前是否安全、是否有独处风险",
                "确认自伤/自杀念头、计划、工具与既往尝试",
                "通知监护人并完成学校危机流程交接",
                "移除危险物品并安排连续陪伴",
                "完成专业转介或就医安排",
                "记录原话、时间、在场人员与后续跟进责任人",
            ],
            "chapter7_mode": "protective",
            "training_modules_disabled": True,
        }
        chapter_8 = report.get("chapter_8_training_modules")
        if isinstance(chapter_8, dict):
            chapter_8["modules"] = []
            chapter_8["active_count"] = 0
            chapter_8["active_module_ids"] = []
            chapter_8["active_modules"] = []
            chapter_8["deferred_modules"] = []
            chapter_8["intro"] = "L4 红色预警期间暂停全部训练模块，优先完成 24 小时危机安全核查。"
        for dimension in _chapter_list(report, "chapter_3_six_dimensions", "dimensions"):
            if isinstance(dimension, dict):
                dimension["training_module_directions"] = ["列为次级观察方向（本阶段暂不展开）"]
                dimension["training_plan_status"] = "次级观察"
    else:
        banner = {
            "level": "L3_ORANGE",
            "severity": 3,
            "visibility": "counselor_only",
            "title": "L3 橙色优先提示：先做校园安全与情绪稳定访谈",
            "message": "检测到 L3 风险维度、单件高危沙具/视觉高危物体，或霸凌/重大变故/拒绝交流等线索；先确认校园安全与情绪稳定，再展开常规发展性建议。",
            "triggers": triggers[:8],
            "recommended_actions": [
                "优先开展校园安全与情绪稳定访谈，确认霸凌、欺凌、威胁、勒索或重大变故。",
                "与班主任、家长核对受测者的同伴关系、上下学路线与可信任成人。",
                "暂缓职业定位与高强度训练，先恢复安全感与基本作息。",
                "根据访谈结果决定是否升级为 L4 或转介专业机构。",
            ],
            "chapter7_mode": "protective",
            "training_modules_disabled": False,
        }

    report["priority_banner"] = banner
    _protective_chapter_content(report, payload, level)
    return level


def _third_person_text(value: str) -> str:
    text = value
    for old in ("你们家孩子", "你家孩子", "你们的孩子", "你家的孩子"):
        text = text.replace(old, "受测者")
    text = text.replace("你们", "受测者").replace("孩子", "受测者")
    return re.sub(r"(?<!迷)你", "受测者", text)


def _enforce_third_person(value: Any, *, skip: bool = False) -> Any:
    if skip:
        return value
    if isinstance(value, dict):
        return {
            key: _enforce_third_person(
                item,
                skip=(skip or key in {"chapter_6_interview", "verification_question", "questions"}),
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_enforce_third_person(item, skip=skip) for item in value]
    if isinstance(value, str):
        return _third_person_text(value)
    return value


def _student_question_text(value: Any) -> str:
    text = str(value or "").strip()
    for old in ("你们家孩子", "你家孩子", "该名学生", "该学生", "这名学生", "这个学生", "该生", "受测者", "孩子"):
        text = text.replace(old, "你")
    if not any(word in text for word in ("你", "您")):
        text = f"你能具体说说，{text}"
    return text


def _parent_question_text(value: Any) -> str:
    text = str(value or "").strip()
    for old in ("该名学生", "该学生", "这名学生", "这个学生", "该生", "受测者"):
        text = text.replace(old, "孩子")
    if "您" not in text and "你们" not in text:
        text = f"您能具体说说，{text}"
    return text


def _teacher_question_text(value: Any) -> str:
    text = str(value or "").strip()
    for old in ("该名学生", "该学生", "这名学生", "这个学生", "该生", "受测者"):
        text = text.replace(old, "孩子")
    if "您" not in text and "你们" not in text:
        text = f"您观察到，{text}"
    return text


def _ensure_dialogue_second_person(report: dict[str, Any]) -> None:
    """第二章验证提问和第六章访谈脚本保留口语第二人称，不转写为“受测者”。"""
    for theme in _chapter_list(report, "chapter_2_imagery", "themes"):
        if isinstance(theme, dict) and theme.get("verification_question"):
            theme["verification_question"] = _student_question_text(theme["verification_question"])

    interview = report.get("chapter_6_interview")
    if not isinstance(interview, dict):
        return
    for item in interview.get("items") or []:
        if not isinstance(item, dict):
            continue
        target = str(item.get("target") or "受测者").strip()
        if target == "家长":
            convert = _parent_question_text
        elif target == "教师":
            convert = _teacher_question_text
        else:
            convert = _student_question_text
        questions = item.get("questions")
        if isinstance(questions, str):
            questions = [questions]
        if isinstance(questions, list):
            item["questions"] = [convert(question) for question in questions if str(question or "").strip()]


def _soften_process_claims(text: Any) -> str:
    value = str(text or "")
    replacements = (
        ("反映出", "可能提示"),
        ("说明受测者", "可能提示受测者"),
        ("说明其", "可能提示其"),
        ("体现出", "可能提示"),
        ("认可度较高", "即时接受度较高（仍需访谈核验）"),
        ("处于放松、信任的表达状态", "可能处于相对放松、愿意表达的状态（需访谈核验）"),
        ("明确的初始构想", "相对清晰的初始构想"),
        ("明确的主动控制意图", "较明显的主动控制意图"),
        ("高度契合", "存在一定呼应"),
        ("提供了过程层面的佐证", "提供了一条过程层面的弱证据"),
    )
    for old, new in replacements:
        value = value.replace(old, new)
    return value


def _ensure_process_analysis(report: dict[str, Any], payload: dict[str, Any]) -> None:
    """过程数据必须进入报告分析；模型缺字段时用同一套指标兜底。"""
    chapter_1 = report.get("chapter_1_overview")
    if not isinstance(chapter_1, dict):
        return
    scene_text = " ".join(str(item) for item in (chapter_1.get("scene_imagery") or []))
    fallback = build_process_analysis(payload, scene_text)
    current = chapter_1.get("process_analysis")
    if not isinstance(current, dict):
        chapter_1["process_analysis"] = fallback
        return
    if not has_process_data(payload):
        chapter_1["process_analysis"] = fallback
        return
    merged = dict(current)
    merged["available"] = True
    merged.setdefault("title", "制作过程动力学观察")
    for key in ("pace", "revision", "terrain_control", "theory_interpretation",
                "integrated_finding", "evidence", "confidence"):
        value = merged.get(key)
        if key == "evidence":
            if not isinstance(value, list) or not [x for x in value if str(x or "").strip()]:
                merged[key] = fallback[key]
            elif any(("process_metrics." in str(x) or "process_telemetry." in str(x) or "=" in str(x)) for x in value):
                merged[key] = fallback[key]
        elif not str(value or "").strip():
            merged[key] = fallback[key]
    for key in ("pace", "revision", "terrain_control", "theory_interpretation", "integrated_finding"):
        merged[key] = _soften_process_claims(merged.get(key))
    chapter_1["process_analysis"] = merged


def _process_integration_fallback(payload: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    metrics = build_process_metrics(payload)
    if not metrics["available"]:
        return {
            "available": False,
            "summary": "本次未采集制作过程数据，六维判断不以操作时序为依据。",
            "referenced_dimensions": [],
            "notes": [],
            "confidence": "低",
        }
    chapter_1 = report.get("chapter_1_overview") or {}
    scene_text = " ".join(str(item) for item in (chapter_1.get("scene_imagery") or []))
    corpus = " ".join(str(payload.get(key) or "") for key in (
        "sandplay_description", "self_narrative", "teacher_observation",
    ))
    corpus += " " + " ".join(str(item.get("label") or "") for item in (payload.get("items") or []) if isinstance(item, dict))
    corpus += " " + scene_text
    family_hit = any(word in corpus for word in (
        "爷爷", "奶奶", "爸爸", "妈妈", "父亲", "母亲", "父母", "家庭", "家人",
        "亲子", "家中", "兄弟", "姐妹",
    ))
    second = "家庭生态协同" if family_hit else "综合动力重塑"

    duration = metrics["total_duration_sec"]
    added = metrics["item_added_total"]
    moved = metrics["item_moved_total"]
    deleted = metrics["item_deleted_total"]
    undo = metrics["undo_count"]
    strokes = metrics["terrain_stroke_count"]
    revision = metrics["revision_actions"]
    per_item = metrics["seconds_per_item"]
    density = metrics["action_density_per_min"]
    terrain_share = metrics["terrain_action_share_pct"]

    cognitive_note = (
        f"制作过程为 {duration} 秒完成 {added} 件、平均 {per_item or '未计算'} 秒/件、"
        f"动作密度 {density or '未计算'} 次/分钟，修改类动作 {revision} 次（删除 {deleted}、"
        f"拖拽 {moved}、撤销 {undo}）。这支持“执行节奏连贯、整体规划较强”的假设，"
        "但快速定型且低修改也可能意味着探索深度有限，因此本维度保持中等置信度，需访谈区分“果断”与“回避深入”。"
    )
    if second == "家庭生态协同":
        second_note = (
            f"推沙/挖水 {strokes} 笔，占全部动作 {terrain_share}%；地形操作说明受测者主动塑形沙面容器。"
            "若家庭人物集中在中心，这一过程更支持“试图安放/容纳家庭情绪”的假设；"
            "若水域或栅栏围住中心，则同时包含边界防御，需要在家庭访谈中核验谁被保护、谁被隔开。"
        )
    else:
        second_note = (
            f"推沙/挖水 {strokes} 笔，占全部动作 {terrain_share}%；在综合动力层面，"
            "主动塑形可理解为为情绪腾出承载空间，而低修改、快节奏则提示当前行动意图较集中。"
            "若场景呈封闭或孤立结构，需把“主动建构”与“提前封闭探索”作为两种竞争假设带进访谈。"
        )

    return {
        "available": True,
        "summary": (
            f"制作过程提供时间维度证据：总耗时 {duration} 秒、放入 {added} 件、"
            f"地形笔触 {strokes} 笔、修改类动作 {revision} 次。"
            f"这些数据主要参与“全学科认知诊断”与“{second}”的判断，"
            "不替代成绩、访谈或教师观察。"
        ),
        "referenced_dimensions": ["全学科认知诊断", second],
        "notes": [cognitive_note, second_note],
        "confidence": "中" if duration and added >= 3 else "低",
    }


def _ensure_process_integration(report: dict[str, Any], payload: dict[str, Any]) -> None:
    chapter_3 = report.get("chapter_3_six_dimensions")
    if not isinstance(chapter_3, dict):
        return
    fallback = _process_integration_fallback(payload, report)
    current = chapter_3.get("process_integration")
    if not isinstance(current, dict):
        chapter_3["process_integration"] = fallback
        return
    if not fallback["available"]:
        chapter_3["process_integration"] = fallback
        return
    merged = dict(current)
    merged["available"] = True
    if not str(merged.get("summary") or "").strip():
        merged["summary"] = fallback["summary"]
    if not isinstance(merged.get("referenced_dimensions"), list) or not merged["referenced_dimensions"]:
        merged["referenced_dimensions"] = fallback["referenced_dimensions"]
    if not isinstance(merged.get("notes"), list) or not [x for x in merged["notes"] if str(x or "").strip()]:
        merged["notes"] = fallback["notes"]
    if not str(merged.get("confidence") or "").strip():
        merged["confidence"] = fallback["confidence"]
    chapter_3["process_integration"] = merged


def _guard_process_integration(report: dict[str, Any], payload: dict[str, Any]) -> None:
    """防止把低修改/无删除直接推断成家庭关系正向或动力未耗竭。"""
    chapter_3 = report.get("chapter_3_six_dimensions")
    if not isinstance(chapter_3, dict):
        return
    current = chapter_3.get("process_integration")
    if not isinstance(current, dict) or not current.get("available"):
        return
    fallback = _process_integration_fallback(payload, report)
    if not fallback["available"]:
        chapter_3["process_integration"] = fallback
        return
    refs = [str(x).strip() for x in (current.get("referenced_dimensions") or []) if str(x).strip()]
    notes = [str(x).strip() for x in (current.get("notes") or []) if str(x).strip()]
    serialized = current.get("summary", "") + " " + " ".join(notes)
    overclaims = ("整体正向", "未出现耗竭", "无选择困难", "支持了", "认可度较高", "处于放松、信任")
    if any(marker in serialized for marker in overclaims) or len(refs) < 2:
        chapter_3["process_integration"] = fallback
        return
    allowed = set(refs)
    filtered = []
    for note in notes:
        prefix = note.split("维度", 1)[0].strip()
        if prefix in allowed:
            filtered.append(_soften_process_claims(note))
    if len(filtered) < 2:
        chapter_3["process_integration"] = fallback
        return
    current["notes"] = filtered
    current["summary"] = _soften_process_claims(current.get("summary"))
    chapter_3["process_integration"] = current


def _clip_text(value: Any, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip("，。；; ") + "…"


def _ensure_self_image_section(report: dict[str, Any], payload: dict[str, Any]) -> None:
    chapter_2 = report.get("chapter_2_imagery")
    if not isinstance(chapter_2, dict):
        return
    name = _clip_text(payload.get("self_image"), 80)
    note = _clip_text(payload.get("self_image_note"), 300)
    if not name:
        chapter_2["self_image"] = {
            "name": "",
            "note": note,
            "hypothesis": "",
            "alternative_hypothesis": "",
            "verification_question": "",
            "risk_boundary": "自我像仅用于访谈假设，不直接决定风险等级。",
        }
        return
    current = chapter_2.get("self_image") if isinstance(chapter_2.get("self_image"), dict) else {}
    hypothesis = _clip_text(current.get("hypothesis"), 260)
    alternative = _clip_text(current.get("alternative_hypothesis"), 260)
    question = _clip_text(current.get("verification_question"), 180)
    if not hypothesis:
        hypothesis = (
            f"受测者选择「{name}」作为自我像，可能提示其此刻以某种姿态或状态表征自己；"
            "这既可能是当下体验，也可能是愿望、保护性象征或对重要他人的认同，不能单凭该符号定性。"
        )
    if not alternative:
        alternative = (
            f"「{name}」也可能承担保护、理想化或防御功能，需结合沙盘位置、代表沙具、"
            "自述与访谈区分“真实状态”与“愿望/认同”。"
        )
    if not question:
        question = f"你选择「{name}」作为此刻的自己，它最像你现在的哪一部分？"
    chapter_2["self_image"] = {
        "name": name,
        "note": note,
        "hypothesis": hypothesis,
        "alternative_hypothesis": alternative,
        "verification_question": _student_question_text(question),
        "risk_boundary": "自我像仅用于访谈假设，不直接决定风险等级；风险仍需沙盘结构、文本、过程与量表证据。",
    }


def _parse_iso_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _ensure_longitudinal_comparison(report: dict[str, Any], payload: dict[str, Any]) -> None:
    previous = payload.get("_previous_assessment")
    if not isinstance(previous, dict) or not previous:
        report["longitudinal_comparison"] = {
            "available": False,
            "comparability": "unavailable",
            "note": "本次没有可用的同一学生历史报告；未做跨报告比较。",
            "risk_changes": [],
            "previous_date": "",
            "days_between": None,
        }
        return

    current_levels = _risk_dimension_levels(report)
    previous_levels = {
        str(item.get("key") or ""): str(item.get("level") or "").upper()
        for item in (previous.get("risk_dimensions") or [])
        if isinstance(item, dict) and str(item.get("key") or "")
    }
    changes: list[dict[str, str]] = []
    improved = 0
    worsened = 0
    stable = 0
    for key, name in RISK_DIMENSIONS:
        before = previous_levels.get(key, "")
        after = current_levels.get(key, "")
        if before not in _RISK_LABELS or after not in _RISK_LABELS:
            changes.append({
                "key": key,
                "name": name,
                "previous_level": before,
                "current_level": after,
                "direction": "unknown",
                "text": "上次或本次缺少该项分级，无法比较",
            })
            continue
        before_rank = int(before[1])
        after_rank = int(after[1])
        if after_rank < before_rank:
            direction = "improved"
            improved += 1
            text = f"较上次下降（{_risk_label(before)} → {_risk_label(after)}）"
        elif after_rank > before_rank:
            direction = "worsened"
            worsened += 1
            text = f"较上次上升（{_risk_label(before)} → {_risk_label(after)}）"
        else:
            direction = "stable"
            stable += 1
            text = f"与上次持平（{_risk_label(after)}）"
        changes.append({
            "key": key,
            "name": name,
            "previous_level": before,
            "current_level": after,
            "direction": direction,
            "text": text,
        })

    current_at = _parse_iso_datetime((report.get("meta") or {}).get("generated_at"))
    previous_at = _parse_iso_datetime(previous.get("created_at") or previous.get("generated_at"))
    days_between = None
    if current_at and previous_at:
        days_between = max(0, (current_at - previous_at).days)

    limitations: list[str] = []
    missing_previous_keys = [name for key, name in RISK_DIMENSIONS if key not in previous_levels]
    if previous.get("lean_only"):
        limitations.append("上次为低投射量样本，风险分级可比性有限")
    if days_between is not None and days_between > 180:
        limitations.append("两次间隔超过 180 天，趋势需结合期间事件")
    if not previous_levels:
        limitations.append("上次报告缺少九维风险数据")
    elif missing_previous_keys:
        limitations.append(f"上次报告缺少{len(missing_previous_keys)}个维度（{'、'.join(missing_previous_keys)}），仅按可对齐维度比较")
    if str(previous.get("engine") or "").lower() == "demo":
        limitations.append("上次为本地演示报告")
    comparability = "limited" if limitations else "comparable"
    previous_count = sum(
        1 for level in previous_levels.values()
        if level in {"L2", "L3", "L4"}
    )
    current_count = sum(
        1 for level in current_levels.values()
        if level in {"L2", "L3", "L4"}
    )
    report["longitudinal_comparison"] = {
        "available": True,
        "comparability": comparability,
        "note": "；".join(limitations) if limitations else "同一学生、同一九维口径，可用于趋势参考。",
        "previous_report_no": str(previous.get("report_no") or ""),
        "previous_date": str(previous.get("created_at") or previous.get("generated_at") or ""),
        "days_between": days_between,
        "previous_self_image": str(previous.get("self_image") or ""),
        "previous_representative_item_name": str(previous.get("representative_item_name") or ""),
        "previous_risk_count": previous_count,
        "current_risk_count": current_count,
        "improved": improved,
        "worsened": worsened,
        "stable": stable,
        "risk_changes": changes,
    }


def _first_interview_question(report: dict[str, Any]) -> str:
    chapter_6 = report.get("chapter_6_interview")
    if isinstance(chapter_6, dict):
        for item in (chapter_6.get("items") or []):
            if not isinstance(item, dict):
                continue
            for question in (item.get("questions") or []):
                text = _clip_text(question, 180)
                if text:
                    return text
    chapter_2 = report.get("chapter_2_imagery")
    if isinstance(chapter_2, dict):
        for theme in (chapter_2.get("themes") or []):
            if isinstance(theme, dict) and theme.get("verification_question"):
                return _clip_text(theme["verification_question"], 180)
    chapter_9 = report.get("chapter_9_general_advice")
    if isinstance(chapter_9, dict):
        for item in (chapter_9.get("growth_mindset") or []):
            if str(item or "").strip():
                return _clip_text(item, 180)
    return "先由心理老师结合访谈核实本次沙盘线索，再决定下一步支持方式。"


def _ensure_summary_card(report: dict[str, Any], payload: dict[str, Any]) -> None:
    chapter_1 = report.get("chapter_1_overview") if isinstance(report.get("chapter_1_overview"), dict) else {}
    chapter_2 = report.get("chapter_2_imagery") if isinstance(report.get("chapter_2_imagery"), dict) else {}
    chapter_5 = report.get("chapter_5_risk") if isinstance(report.get("chapter_5_risk"), dict) else {}
    chapter_6 = report.get("chapter_6_interview") if isinstance(report.get("chapter_6_interview"), dict) else {}
    chapter_7 = report.get("chapter_7_career") if isinstance(report.get("chapter_7_career"), dict) else {}

    self_image = chapter_2.get("self_image") if isinstance(chapter_2.get("self_image"), dict) else {}
    self_image_name = _clip_text(self_image.get("name") or payload.get("self_image"), 80)
    representative = _clip_text(
        payload.get("representative_item_name") or chapter_1.get("representative_item_name"),
        80,
    )
    theme_names: list[str] = []
    for theme in (chapter_2.get("themes") or []):
        if isinstance(theme, dict):
            name = _clip_text(theme.get("theme"), 60)
            if name and name not in theme_names:
                theme_names.append(name)
        if len(theme_names) >= 3:
            break
    themes_text = "、".join(theme_names[:2]) if theme_names else (representative or "当前沙盘的主要场景")

    risk_levels = _risk_dimension_levels(report)
    risk_count = sum(1 for level in risk_levels.values() if level in {"L2", "L3", "L4"})
    highest_level = "L1"
    for level in risk_levels.values():
        if level in _RISK_LABELS and int(level[1]) > int(highest_level[1]):
            highest_level = level
    comparison = report.get("longitudinal_comparison") if isinstance(report.get("longitudinal_comparison"), dict) else {}
    comparison_public = {
        "available": bool(comparison.get("available")),
        "previous_date": str(comparison.get("previous_date") or ""),
        "days_between": comparison.get("days_between"),
        "comparability": str(comparison.get("comparability") or "unavailable"),
        "note": str(comparison.get("note") or ""),
    }

    strengths: list[str] = []
    for item in (chapter_7.get("strengths") or []):
        value = _clip_text(item, 70)
        if value and value not in strengths:
            strengths.append(value)
        if len(strengths) >= 1:
            break
    resource_text = strengths[0] if strengths else "当前沙盘中可见的资源线索有限，需结合访谈补充"

    signals: list[dict[str, str]] = []
    if self_image_name:
        signals.append({"label": "自我像", "value": self_image_name, "tone": "neutral"})
    signals.append({"label": "核心意象", "value": representative or "未填写", "tone": "neutral"})
    signals.append({"label": "主要主题", "value": themes_text, "tone": "neutral"})
    signals.append({"label": "资源线索", "value": resource_text, "tone": "resource"})
    if risk_count:
        signals.append({
            "label": "需关注",
            "value": f"{risk_count} 项，最高 {_risk_label(highest_level)}",
            "tone": "attention",
        })
    else:
        signals.append({
            "label": "需关注",
            "value": f"当前未见 L2–L4 风险维度；仍需访谈核验",
            "tone": "neutral",
        })
    signals = signals[:5]

    next_step = _clip_text(
        self_image.get("verification_question") or _first_interview_question(report),
        180,
    )
    if self_image_name:
        headline = f"本次以「{self_image_name}」作为自我像，沙盘整体围绕「{themes_text}」展开。"
        public_headline = f"你选择了「{self_image_name}」作为此刻的自己，沙盘里还有「{themes_text}」这些线索。"
    else:
        headline = f"本次沙盘以「{representative or '当前场景'}」为核心意象，整体围绕「{themes_text}」展开。"
        public_headline = f"你的沙盘里出现了「{representative or '当前场景'}」和「{themes_text}」这些线索。"

    public_signals: list[dict[str, str]] = []
    if self_image_name:
        public_signals.append({"label": "你选择的自我像", "value": self_image_name, "tone": "neutral"})
    public_signals.append({"label": "沙盘里的核心意象", "value": representative or "未填写", "tone": "neutral"})
    public_signals.append({"label": "主要线索", "value": themes_text, "tone": "neutral"})
    public_signals.append({"label": "你已经有的资源", "value": resource_text, "tone": "resource"})
    public_signals = public_signals[:5]

    report["summary_card"] = {
        "headline": headline,
        "signals": signals,
        "next_step": next_step,
        "risk_overview": {
            "count": risk_count,
            "highest_level": highest_level,
            "highest_label": _risk_label(highest_level),
            "total_dimensions": len(RISK_DIMENSIONS),
            "previous_count": comparison.get("previous_risk_count", 0) if comparison.get("available") else 0,
            "previous": comparison_public,
            "improved": comparison.get("improved", 0),
            "worsened": comparison.get("worsened", 0),
            "stable": comparison.get("stable", 0),
        },
        "public": {
            "headline": public_headline,
            "signals": public_signals,
            "next_step": next_step,
            "previous": comparison_public,
            "note": "本页为发展性评估摘要，不含风险分级；具体支持方式以心理老师沟通为准。",
        },
    }


def _collect_quality_report(
    report: dict[str, Any],
    sample_quality: dict[str, Any],
    priority_level: str,
) -> tuple[list[str], list[dict[str, str]], str]:
    flags = list(sample_quality.get("quality_flags") or [])
    warnings = [dict(item) for item in (sample_quality.get("quality_warnings") or []) if isinstance(item, dict)]

    def add(code: str, message: str) -> None:
        if code in flags:
            return
        flags.append(code)
        severity, _ = QUALITY_FLAG_META.get(code, ("warning", code))
        warnings.append({"code": code, "severity": severity, "message": message})

    chapter5 = report.get("chapter_5_risk") if isinstance(report.get("chapter_5_risk"), dict) else {}
    consistency = str(chapter5.get("consistency_warning") or "").strip()
    if consistency:
        add("RISK_LEVEL_CONFLICT", consistency)

    chapter8 = report.get("chapter_8_training_modules") if isinstance(report.get("chapter_8_training_modules"), dict) else {}
    active_count = int(chapter8.get("active_count") or 0)
    if priority_level in ("L3_ORANGE", "L4_RED") and active_count > 1:
        add("TRAINING_INTENSITY_CONFLICT", "当前处于优先关注/危机阶段，但第八章仍启动超过 1 个模块；建议收束为低强度优先模块。")

    chapter7 = report.get("chapter_7_career") if isinstance(report.get("chapter_7_career"), dict) else {}
    chapter4 = report.get("chapter_4_academic") if isinstance(report.get("chapter_4_academic"), dict) else {}
    has_scores = bool(sample_quality.get("has_scores")) or any(
        isinstance(row, dict) and row.get("score") is not None
        for row in (chapter4.get("subjects") or [])
    )
    career_blob = " ".join(
        str(chapter7.get(field) or "")
        for field in ("summary", "evidence_note", "career_resume_note")
    ) + " " + " ".join(str(item) for item in (chapter7.get("strengths") or []))
    if not has_scores and _career_text_has_score_claim(career_blob):
        add("SCORE_BASIS_MISMATCH", "报告职业章节引用了成绩依据，但本次没有可读成绩；已要求改为不结合成绩排序。")

    meta = report.get("meta") if isinstance(report.get("meta"), dict) else {}
    screen = meta.get("holistic_screen") if isinstance(meta.get("holistic_screen"), dict) else {}
    if is_high_risk(screen):
        labels = "、".join(str(item) for item in (screen.get("readable_text") or [])[:4]).strip()
        add(
            "HOLISTIC_RISK_SYMBOL",
            f"沙盘整体构图形成明确的高危文字/符号{f'（{labels}）' if labels else ''}，已按 L4 重大风险处理，需立即人工安全核查。",
        )
    elif screen.get("status") == "failed":
        add(
            "HOLISTIC_SCREEN_UNAVAILABLE",
            "整体构图安全筛查未完成，当前报告不能据此排除整体画面高危语义；需由咨询师直接查看原图并人工复核。",
        )
    visual_high = visual_high_objects(screen)
    if visual_high:
        labels = "、".join(
            str(item.get("label") or item.get("type_label") or "高危物体")
            for item in visual_high[:4]
        )
        add(
            "VISUAL_RISK_OBJECT",
            f"画面发现视觉高危物体：{labels}；已结合位置、朝向、人物关系和场景语境分级，需咨询师核对原图。",
        )
    if str(meta.get("engine") or "").strip().lower() == "demo":
        add("DEMO_ENGINE", "当前为本地示例报告，未接入多模态模型；内容用于流程演示，不能直接作为真实评估结论交付。")

    severity_rank = {"info": 0, "warning": 1, "critical": 2}
    quality_level = "ok"
    for item in warnings:
        if severity_rank.get(str(item.get("severity")), 0) > severity_rank.get(quality_level, -1):
            quality_level = str(item.get("severity") or "warning")
    return flags, warnings, quality_level


def apply_report_quality_gates(
    report: dict[str, Any],
    *,
    payload: dict[str, Any],
    transcript_url: str | None,
) -> dict[str, Any]:
    """服务端质量门控：动态评估依据、低投射量提示、原始记录与训练模块优先级。"""
    meta = report.setdefault("meta", {})
    sample_quality = build_sample_quality(payload, transcript_url)
    process_note = _process_note(payload)
    terrain_text = terrain_observation(payload)
    raw_record = _raw_record_echo(payload)
    meta["assessment_basis"] = _report_basis(payload, transcript_url)
    meta["sample_quality"] = sample_quality
    meta["process_metrics"] = build_process_metrics(payload)
    meta["client_inputs"] = {
        "sandplay_description": raw_record["sandplay_description"],
        "self_narrative": raw_record["self_narrative"],
        "teacher_observation": raw_record["teacher_observation"],
        "representative_item_name": str(payload.get("representative_item_name") or "").strip(),
        "self_image": str(payload.get("self_image") or "").strip(),
        "self_image_note": str(payload.get("self_image_note") or "").strip(),
        "terrain_metrics": payload.get("terrain_metrics") or {},
        "terrain_observation": terrain_text,
        "process_telemetry": _process_telemetry(payload),
        "interaction_summary": payload.get("interaction_summary") or {},
        "process_note": process_note,
    }
    report["raw_record_echo"] = raw_record
    holistic_screen = payload.get("_holistic_screen") if isinstance(payload.get("_holistic_screen"), dict) else {}
    if holistic_screen:
        meta["holistic_screen"] = holistic_screen
        meta["holistic_screen_risk"] = (
            "high" if is_high_risk(holistic_screen) else str(holistic_screen.get("risk_level") or "unknown")
        )
    chapter_1 = report.get("chapter_1_overview")
    if isinstance(chapter_1, dict):
        representative = str(payload.get("representative_item_name") or chapter_1.get("representative_item_name") or "").strip()
        if representative:
            chapter_1["representative_item_name"] = representative
        chapter_1["terrain_observation"] = terrain_text
        chapter_1["process_observation"] = process_note
        _merge_holistic_screen(report, holistic_screen)
        _ensure_process_analysis(report, payload)
    _ensure_self_image_section(report, payload)
    _ensure_process_integration(report, payload)
    _guard_process_integration(report, payload)
    priority_level = _apply_priority_routing(report, payload, transcript_url)
    _apply_theory_guardrails(report, payload, transcript_url)
    _apply_risk_guardrails(report, sample_quality)
    _apply_risk_consistency(report, priority_level)
    _cap_low_sample_confidence(report, sample_quality)
    if priority_level != "L4_RED":
        max_active = 1 if (
            priority_level == "L3_ORANGE"
            or sample_quality.get("low_projection")
            or sample_quality.get("evidence_level") == "minimal"
        ) else 2
        _apply_training_gates(report, sample_quality, max_active=max_active)
        _backfill_dimension_training(report)
    _rewrite_career_for_evidence(report, sample_quality, priority_level)
    _ensure_chapter9(report)
    _ensure_longitudinal_comparison(report, payload)
    report["chapter_5_risk"]["visibility"] = "counselor_only"
    for chapter_key, chapter_value in report.items():
        if re.fullmatch(r"chapter_[1-9]_[a-z_]+", str(chapter_key)) and chapter_key != "chapter_6_interview":
            report[chapter_key] = _enforce_third_person(chapter_value)
    _ensure_dialogue_second_person(report)
    _ensure_summary_card(report, payload)
    flags, warnings, quality_level = _collect_quality_report(report, sample_quality, priority_level)
    meta["quality_flags"] = flags
    meta["quality_warnings"] = warnings
    meta["quality_level"] = quality_level
    return report


def normalize_meta(
    report: dict[str, Any],
    *,
    payload: dict[str, Any],
    image_url: str,
    transcript_url: str | None,
    engine: str,
    engine_note: str = "",
) -> dict[str, Any]:
    student = payload.get("student") or {}
    meta = report.setdefault("meta", {})
    now = datetime.now(timezone.utc)
    meta.update({
        "report_no": f"PS-{now.strftime('%Y%m%d-%H%M%S')}",
        "generated_at": now.isoformat(),
        "assessment_source": "沙盘作品评估",
        "grade_level": student.get("grade_level") or meta.get("grade_level") or "未填写",
        "gender": student.get("gender") or meta.get("gender") or "未填写",
        "student_name": student.get("name") or "匿名受测者",
        "student_no": student.get("student_no") or "",
        "self_image": str(payload.get("self_image") or "").strip(),
        "self_image_note": str(payload.get("self_image_note") or "").strip(),
        "disclaimer": "发展性心理评估参考·非临床诊断",
        "engine": engine,
        "engine_note": engine_note,
        "demo_report": engine == "demo",
    })
    report["chapter_1_overview"]["sandplay_image_url"] = image_url
    chapter_4 = report["chapter_4_academic"]
    structured_scores = structured_academic_scores(payload)
    if structured_scores:
        chapter_4["structured_scores"] = structured_scores
        chapter_4["score_source"] = "structured_entry"
        if not transcript_url:
            note = "结构化成绩由受测者录入，待与成绩单核对。"
            existing_notes = chapter_4.get("notes")
            notes = existing_notes if isinstance(existing_notes, list) else ([existing_notes] if existing_notes else [])
            if note not in notes:
                notes.append(note)
            chapter_4["notes"] = notes
    if transcript_url:
        chapter_4["transcript_provided"] = True
        chapter_4["transcript_image_url"] = transcript_url
        chapter_4["score_source"] = "transcript_image" if not structured_scores else "mixed"
    else:
        chapter_4["transcript_provided"] = bool(structured_scores)
        chapter_4["transcript_image_url"] = ""
    apply_report_quality_gates(report, payload=payload, transcript_url=transcript_url)
    return report


async def screen_holistic_image(sandplay_image: bytes) -> dict[str, Any]:
    """独立于九维风险表的整体构图安全筛查。

    必需性：九维模型容易被“单个沙具正常”牵制，漏掉由水域/沙丘/留白共同
    构成的“死”“亡”等高危文字。这里先只看整体构图，结果由服务端强制
    接入 priority_banner，不能由主报告自行降级。
    """
    if not MULTIMODAL_API_KEY:
        return normalize_screen(
            {"risk_level": "unknown", "risk_evidence": "未配置多模态模型"},
            status="not_configured",
        )

    body = {
        "model": MULTIMODAL_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": HOLISTIC_SCREEN_PROMPT},
                {"type": "image_url", "image_url": {"url": _data_uri(sandplay_image, "sandplay.png"), "detail": "high"}},
            ],
        }],
        "temperature": 0,
        "max_tokens": 1800,
    }
    if "volces.com" in MULTIMODAL_BASE_URL:
        body["thinking"] = {"type": "disabled"}
    headers = {"Authorization": f"Bearer {MULTIMODAL_API_KEY}", "Content-Type": "application/json"}
    timeout = min(max(MULTIMODAL_TIMEOUT_SECONDS, 30), 120)
    last_error = ""
    for attempt in range(2):
        if attempt:
            await asyncio.sleep(2)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(f"{MULTIMODAL_BASE_URL}/chat/completions", headers=headers, json=body)
                response.raise_for_status()
                data = response.json()
            message = (data.get("choices") or [{}])[0].get("message") or {}
            content = message.get("content")
            if isinstance(content, list):
                content = "\n".join(part.get("text", "") for part in content if isinstance(part, dict))
            if not isinstance(content, str) or not content.strip():
                raise ValueError("整体构图筛查返回为空")
            parsed = parse_json_object(content)
            if not isinstance(parsed, dict):
                raise ValueError("整体构图筛查不是 JSON 对象")
            result = normalize_screen(parsed, status="ok")
            result["model"] = MULTIMODAL_MODEL
            result["usage"] = data.get("usage") if isinstance(data.get("usage"), dict) else {}
            result["attempts"] = attempt + 1
            return result
        except Exception as exc:  # 筛查失败不静默放行，交给上层转 L3 人工复核
            last_error = type(exc).__name__
    result = normalize_screen({}, status="failed")
    result["error"] = last_error or "UNKNOWN"
    return result


async def call_multimodal(
    payload: dict[str, Any],
    sandplay_image: bytes,
    transcript_image: bytes | None,
    image_url: str,
    transcript_url: str | None,
) -> dict[str, Any]:
    user_content: list[dict[str, Any]] = [
        {"type": "text", "text": build_user_prompt(payload, image_url, transcript_url)},
        {"type": "image_url", "image_url": {"url": _data_uri(sandplay_image, "sandplay.png"), "detail": "high"}},
    ]
    if transcript_image:
        user_content.append({"type": "text", "text": "下面是受测者上传的成绩单图片，请逐科读取。"})
        user_content.append({"type": "image_url", "image_url": {"url": _data_uri(transcript_image, "transcript.png"), "detail": "high"}})

    body = {
        "model": MULTIMODAL_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.2,
        "max_tokens": 24000,
    }
    # 方舟的 Doubao Seed 2.0 默认开启深度思考，思考 token 会挤占报告 JSON 的输出额度。
    # 结构化九章报告不需要额外思维链，这里在方舟请求中显式关闭，避免报告被截断。
    if "volces.com" in MULTIMODAL_BASE_URL:
        body["thinking"] = {"type": "disabled"}
    headers = {"Authorization": f"Bearer {MULTIMODAL_API_KEY}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=MULTIMODAL_TIMEOUT_SECONDS) as client:
        response = await client.post(f"{MULTIMODAL_BASE_URL}/chat/completions", headers=headers, json=body)
        response.raise_for_status()
        data = response.json()

    message = (data.get("choices") or [{}])[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        content = "\n".join(part.get("text", "") for part in content if isinstance(part, dict))
    if not isinstance(content, str) or not content.strip():
        raise ValueError("多模态模型返回为空")
    parsed = parse_json_object(content)
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    if isinstance(parsed, dict):
        meta = parsed.setdefault("meta", {})
        if isinstance(meta, dict):
            meta["generation_usage"] = usage
    return validate_report(parsed)


async def generate_report(
    payload: dict[str, Any],
    *,
    sandplay_image: bytes,
    transcript_image: bytes | None,
    image_url: str,
    transcript_url: str | None,
    allow_demo_fallback: bool | None = None,
) -> tuple[dict[str, Any], str]:
    allow_demo = ALLOW_DEMO_REPORT if allow_demo_fallback is None else allow_demo_fallback
    if MULTIMODAL_API_KEY:
        payload = dict(payload)
        payload["_holistic_screen"] = await screen_holistic_image(sandplay_image)
        try:
            report = await call_multimodal(payload, sandplay_image, transcript_image, image_url, transcript_url)
            report = normalize_meta(
                report, payload=payload, image_url=image_url, transcript_url=transcript_url,
                engine="multimodal", engine_note="多模态模型生成，经九章节结构校验",
            )
            return report, "multimodal"
        except Exception:  # 生产默认不降级，演示模式只保留通用说明
            if not allow_demo:
                raise
            note = "多模态调用失败，已降级为本地演示报告；请查看服务端日志定位原因"
    else:
        note = "未配置 MULTIMODAL_API_KEY，使用本地演示报告；配置密钥后自动切换多模态生成"

    report = build_demo_report(
        payload, sandplay_image_url=image_url, transcript_image_url=transcript_url, engine_note=note,
    )
    report = validate_report(report)
    report = normalize_meta(
        report, payload=payload, image_url=image_url, transcript_url=transcript_url,
        engine="demo", engine_note=note,
    )
    return report, "demo"
