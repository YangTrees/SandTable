from __future__ import annotations

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
from .prompt import SYSTEM_PROMPT, build_user_prompt
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
from .utils import clean_json_text


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
    report["chapter_8_training_modules"]["modules"] = _ordered_fixed_rows(
        modules, expected_modules, "chapter_8_training_modules.modules", _MODULE_ALIASES
    )

    for key, title in CHAPTER_TITLES.items():
        chapter = report.get(key)
        if not isinstance(chapter, dict):
            raise ValueError(f"缺少 {key}")
        chapter.setdefault("title", title)
    return report


def _heightmap_max_abs(payload: dict[str, Any]) -> float:
    heightmap = payload.get("heightmap") or {}
    values = heightmap.get("values") or []
    if not isinstance(values, list):
        return 0.0
    max_abs = 0.0
    for value in values:
        try:
            max_abs = max(max_abs, abs(float(value)))
        except (TypeError, ValueError):
            continue
    return max_abs


def _has_terrain_image(payload: dict[str, Any]) -> bool:
    return any(
        bool(payload.get(key))
        for key in ("terrain_image_url", "terrain_image_path", "terrain_heightmap_url", "terrain_map_url")
    )


def _terrain_metric_bool(payload: dict[str, Any], key: str) -> bool | None:
    metrics = payload.get("terrain_metrics")
    if not isinstance(metrics, dict) or key not in metrics:
        return None
    value = metrics.get(key)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "是", "已编辑"}


def _has_terrain(payload: dict[str, Any]) -> bool:
    edited = _terrain_metric_bool(payload, "terrain_edited")
    if edited is not None:
        return edited or _has_terrain_image(payload)
    if _has_terrain_image(payload):
        return True
    return _heightmap_max_abs(payload) > 0.5


def _terrain_observation(payload: dict[str, Any]) -> str:
    metrics = payload.get("terrain_metrics") if isinstance(payload.get("terrain_metrics"), dict) else {}
    summary = str(metrics.get("terrain_summary") or "").strip()
    if summary:
        return summary
    if _has_terrain(payload):
        water = metrics.get("water_area_pct")
        mound = metrics.get("mound_area_pct")
        relief = metrics.get("elevation_range")
        parts = []
        if isinstance(water, (int, float)) and water > 0:
            parts.append(f"挖出水域约占 {round(float(water), 1)}%")
        if isinstance(mound, (int, float)) and mound > 0:
            parts.append(f"隆起沙丘/沙岛约占 {round(float(mound), 1)}%")
        if isinstance(relief, (int, float)) and relief > 0:
            parts.append(f"高程差约 {round(float(relief), 1)}")
        return "已进行明显地形塑形：" + "，".join(parts) + "。" if parts else "已进行地形塑形。"
    return "沙面基本平整，未进行明显地形塑形。"


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _process_telemetry(payload: dict[str, Any]) -> dict[str, Any]:
    telemetry = payload.get("process_telemetry") if isinstance(payload.get("process_telemetry"), dict) else {}
    legacy = payload.get("interaction_summary") if isinstance(payload.get("interaction_summary"), dict) else {}

    def value(*keys: str) -> Any:
        for key in keys:
            if key in telemetry:
                return telemetry.get(key)
            if key in legacy:
                return legacy.get(key)
        return 0

    bury_actions = telemetry.get("bury_actions")
    if not isinstance(bury_actions, list):
        bury_actions = legacy.get("bury_actions") if isinstance(legacy.get("bury_actions"), list) else []
        if not isinstance(bury_actions, list):
            bury_actions = []
    return {
        "total_duration_sec": _safe_int(value("total_duration_sec", "duration_seconds", "elapsed_seconds", "total_seconds")),
        "item_added_total": _safe_int(value("item_added_total", "place_count")),
        "item_deleted_total": _safe_int(value("item_deleted_total", "delete_count", "remove_count", "removed_count")),
        "hesitation_count": _safe_int(value("hesitation_count", "drag_count", "move_count")),
        "terrain_stroke_count": _safe_int(value("terrain_stroke_count", "brush_strokes", "raise_sand_count")),
        "bury_actions": [x for x in bury_actions if isinstance(x, dict)][:20],
        "destructive_loops": _safe_int(value("destructive_loops")),
        "undo_count": _safe_int(value("undo_count")),
    }


def _has_process_data(payload: dict[str, Any]) -> bool:
    telemetry = _process_telemetry(payload)
    if any(telemetry[key] for key in (
        "total_duration_sec", "item_added_total", "item_deleted_total",
        "hesitation_count", "terrain_stroke_count", "destructive_loops", "undo_count",
    )) or telemetry["bury_actions"]:
        return True
    summary = payload.get("interaction_summary") or {}
    if not isinstance(summary, dict):
        return False
    process_keys = {
        "duration_seconds", "elapsed_seconds", "total_seconds", "total_duration_sec",
        "drag_count", "delete_count", "item_added_total", "item_deleted_total",
        "hesitation_count", "undo_count", "undo_steps", "brush_strokes",
        "terrain_stroke_count", "bury_actions", "destructive_loops", "last_item_dwell_seconds",
    }
    return any(key in summary for key in process_keys)


def _format_duration(seconds: int) -> str:
    if seconds <= 0:
        return "未记录"
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours} 小时 {minutes} 分 {sec} 秒"
    if minutes:
        return f"{minutes} 分 {sec} 秒"
    return f"{sec} 秒"


def _process_note(payload: dict[str, Any]) -> str:
    telemetry = _process_telemetry(payload)
    if not _has_process_data(payload):
        return "本次未采集制作耗时、推沙/挖水、修改犹豫次数；仅记录当前交互摘要。"
    parts = [
        f"制作总耗时 {_format_duration(telemetry['total_duration_sec'])}",
        f"累计放入 {telemetry['item_added_total']} 件",
        f"删除/撤回 {telemetry['item_deleted_total']} 件",
        f"拖拽调整 {telemetry['hesitation_count']} 次",
        f"推沙/挖水 {telemetry['terrain_stroke_count']} 笔",
    ]
    if telemetry["bury_actions"]:
        parts.append(f"掩埋人物 {len(telemetry['bury_actions'])} 次")
    if telemetry["destructive_loops"]:
        parts.append(f"短时反复放删 {telemetry['destructive_loops']} 次")
    if telemetry["undo_count"]:
        parts.append(f"撤销 {telemetry['undo_count']} 次")
    return "；".join(parts) + "。"


def _raw_record_echo(payload: dict[str, Any]) -> dict[str, str]:
    return {
        "sandplay_description": str(payload.get("sandplay_description") or ""),
        "self_narrative": str(payload.get("self_narrative") or ""),
        "teacher_observation": str(payload.get("teacher_observation") or ""),
    }


def _report_basis(payload: dict[str, Any], transcript_url: str | None) -> list[str]:
    items = payload.get("items") or []
    grid = payload.get("grid_distribution") or {}
    basis = ["沙盘作品照片1张"]
    if grid.get("cells"):
        basis.append("九宫格空间分布")
    if items:
        basis.append("沙具使用数据")
    if _terrain_metric_bool(payload, "terrain_edited") is True or _has_terrain_image(payload):
        basis.append("沙盘地形高度图")
    if payload.get("representative_item_id") or payload.get("representative_item_name"):
        basis.append("代表沙具1件")
    if str(payload.get("sandplay_description") or "").strip():
        basis.append("受测者沙盘描述1段")
    if str(payload.get("self_narrative") or "").strip():
        basis.append("受测者自述文本")
    if str(payload.get("teacher_observation") or "").strip():
        basis.append("教师观察记录")
    if transcript_url:
        basis.append("学习成绩单1张")
    return basis


def _sample_quality(payload: dict[str, Any]) -> dict[str, Any]:
    items = payload.get("items") or []
    grid = payload.get("grid_distribution") or {}
    summary = grid.get("summary") or {}
    item_count = len(items)
    has_terrain = _has_terrain(payload)
    low_projection = item_count < 3 and not has_terrain
    return {
        "item_count": item_count,
        "occupied_cells": summary.get("occupied_cells", 0),
        "has_terrain": has_terrain,
        "terrain_edited": _terrain_metric_bool(payload, "terrain_edited"),
        "terrain_summary": _terrain_observation(payload),
        "heightmap_max_abs": round(_heightmap_max_abs(payload), 4),
        "process_data_available": _has_process_data(payload),
        "low_projection": low_projection,
        "label": "低投射量样本" if low_projection else "常规样本",
    }


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


def _apply_training_gates(report: dict[str, Any], sample_quality: dict[str, Any]) -> None:
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
    if len(ranked) > 1 and ranked[1][0] >= max(2.0, ranked[0][0] - 0.35):
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
        short = _module_short_name(module.get("name"))
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


def _cap_low_sample_confidence(report: dict[str, Any]) -> None:
    """低投射量样本不允许出现“高”置信度，避免用少量沙具做强判断。"""
    for dimension in _chapter_list(report, "chapter_3_six_dimensions", "dimensions"):
        if isinstance(dimension, dict) and str(dimension.get("confidence") or "").strip() == "高":
            dimension["confidence"] = "中"
    for theme in _chapter_list(report, "chapter_2_imagery", "themes"):
        if isinstance(theme, dict) and str(theme.get("confidence") or "").strip() == "高":
            theme["confidence"] = "中"


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
    grid = payload.get("grid_distribution") or {}
    grid_summary = grid.get("summary") or {}
    occupied = int(grid_summary.get("occupied_cells") or 0)
    center_count = int(grid_summary.get("center_count") or 0)
    heightmap = payload.get("heightmap") or {}
    values = [float(v) for v in (heightmap.get("values") or []) if isinstance(v, (int, float))]
    relief = round(max(values) - min(values), 3) if values else 0.0

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
    terrain_text = _terrain_observation(payload)
    return {
        "items_count": len(items),
        "occupied": occupied,
        "center_count": center_count,
        "blank_count": max(0, 9 - occupied),
        "relief": relief,
        "layout_text": layout_text,
        "terrain_text": terrain_text,
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
        result = (
            f"压力与阴影主题共 {clues['pressure_count']} 件，提示情绪负荷可能占用专注带宽；"
            f"{layout}与地形塑形提供计划性、步骤组织和元认知监控的探索线索。"
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

        conclusion = _clean_theory_warning(dimension.get("conclusion"))
        if _EXPLORATION_DISCLAIMER not in conclusion:
            conclusion = (conclusion.rstrip("。") + "。" if conclusion else "") + _EXPLORATION_DISCLAIMER
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
        if level == "L1" and "未见显性" not in str(dimension.get("judgement") or ""):
            judgement = str(dimension.get("judgement") or "").strip().rstrip("。")
            dimension["judgement"] = (
                (judgement + "；" if judgement else "")
                + "该结论仅基于当前沙盘，未见显性线索不等于无风险，需结合访谈/量表核实。"
            )


def _priority_text_blob(payload: dict[str, Any]) -> str:
    return "\n".join(str(payload.get(field) or "") for field in (
        "sandplay_description", "self_narrative", "teacher_observation", "transcript_text"
    ))


def _detect_priority(
    report: dict[str, Any],
    payload: dict[str, Any],
    transcript_url: str | None,
) -> dict[str, Any] | None:
    triggers: list[str] = []
    text_blob = _priority_text_blob(payload)

    high_risk_items = [
        item for item in (payload.get("items") or [])
        if isinstance(item, dict) and str(item.get("risk_tier") or "").lower() == "high_risk"
    ]
    severe_names = [
        str(item.get("label") or item.get("name") or "").strip()
        for item in high_risk_items
        if any(word in str(item.get("label") or item.get("name") or "") for word in _DEATH_ITEM_WORDS)
    ]
    if severe_names:
        triggers.extend(f"高危画面：{name}" for name in severe_names[:4])
    elif len(high_risk_items) >= 1:
        labels = [
            str(item.get("label") or item.get("name") or "高危沙具").strip()
            for item in high_risk_items[:4]
        ]
        triggers.extend(f"高危画面：{label}" for label in labels)

    for match in _L4_TEXT_RE.finditer(text_blob):
        triggers.append(f"自伤/绝望文本：{match.group(1)}")

    if not triggers:
        for word in _HIGH_RISK_ITEM_WORDS:
            if word in text_blob:
                triggers.append(f"高危画面关键词：{word}")
                break

    for match in _DESTRUCTION_TEXT_RE.finditer(text_blob):
        triggers.append(f"掩埋/破坏操作描述：{match.group(1)}")

    telemetry = _process_telemetry(payload)
    if telemetry["bury_actions"]:
        triggers.append(f"制作过程：掩埋人物 {len(telemetry['bury_actions'])} 次")
    if telemetry["destructive_loops"]:
        triggers.append(f"制作过程：短时反复放删 {telemetry['destructive_loops']} 次")

    interaction = payload.get("interaction_summary") or {}
    for key in ("buried_count", "destroyed_count", "delete_count", "removed_count"):
        value = interaction.get(key)
        if isinstance(value, (int, float)) and value >= 1:
            triggers.append(f"操作记录：{key}={int(value)}")

    levels = _risk_dimension_levels(report)
    expected = dict(RISK_DIMENSIONS)
    l4_dimensions = [
        expected.get(key, key) for key, level in levels.items()
        if level == "L4"
    ]
    if l4_dimensions:
        triggers.extend(f"九维风险达 L4：{name}" for name in l4_dimensions)

    if triggers:
        return {"level": "L4_RED", "triggers": list(dict.fromkeys(triggers))}

    l3_dimensions = [
        expected.get(key, key) for key, level in levels.items()
        if level in ("L3", "L4")
    ]
    if l3_dimensions:
        triggers.extend(f"九维风险达 L3：{name}" for name in l3_dimensions)
    for match in _L3_TEXT_RE.finditer(text_blob):
        triggers.append(f"自述/教师观察关键词：{match.group(1)}")

    if triggers:
        return {"level": "L3_ORANGE", "triggers": list(dict.fromkeys(triggers))}
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
            "message": "检测到 L3 风险维度或霸凌/重大变故/拒绝交流等线索，优先确认校园安全与情绪稳定，再展开常规发展性建议。",
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
            key: _enforce_third_person(item, skip=(key == "chapter_6_interview"))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_enforce_third_person(item, skip=skip) for item in value]
    if isinstance(value, str):
        return _third_person_text(value)
    return value


def apply_report_quality_gates(
    report: dict[str, Any],
    *,
    payload: dict[str, Any],
    transcript_url: str | None,
) -> dict[str, Any]:
    """服务端质量门控：动态评估依据、低投射量提示、原始记录与训练模块优先级。"""
    meta = report.setdefault("meta", {})
    sample_quality = _sample_quality(payload)
    process_note = _process_note(payload)
    terrain_observation = _terrain_observation(payload)
    raw_record = _raw_record_echo(payload)
    meta["assessment_basis"] = _report_basis(payload, transcript_url)
    meta["sample_quality"] = sample_quality
    meta["client_inputs"] = {
        "sandplay_description": raw_record["sandplay_description"],
        "self_narrative": raw_record["self_narrative"],
        "teacher_observation": raw_record["teacher_observation"],
        "representative_item_name": str(payload.get("representative_item_name") or "").strip(),
        "terrain_metrics": payload.get("terrain_metrics") or {},
        "terrain_observation": terrain_observation,
        "process_telemetry": _process_telemetry(payload),
        "interaction_summary": payload.get("interaction_summary") or {},
        "process_note": process_note,
    }
    report["raw_record_echo"] = raw_record
    chapter_1 = report.get("chapter_1_overview")
    if isinstance(chapter_1, dict):
        representative = str(payload.get("representative_item_name") or chapter_1.get("representative_item_name") or "").strip()
        if representative:
            chapter_1["representative_item_name"] = representative
        chapter_1["terrain_observation"] = terrain_observation
        chapter_1["process_observation"] = process_note
    if sample_quality.get("low_projection"):
        _cap_low_sample_confidence(report)
    priority_level = _apply_priority_routing(report, payload, transcript_url)
    _apply_theory_guardrails(report, payload, transcript_url)
    _apply_risk_guardrails(report, sample_quality)
    if priority_level != "L4_RED":
        _apply_training_gates(report, sample_quality)
        _backfill_dimension_training(report)
    report["chapter_5_risk"]["visibility"] = "counselor_only"
    for chapter_key, chapter_value in report.items():
        if re.fullmatch(r"chapter_[1-9]_[a-z_]+", str(chapter_key)) and chapter_key != "chapter_6_interview":
            report[chapter_key] = _enforce_third_person(chapter_value)
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
        "disclaimer": "发展性心理评估参考·非临床诊断",
        "engine": engine,
        "engine_note": engine_note,
    })
    report["chapter_1_overview"]["sandplay_image_url"] = image_url
    chapter_4 = report["chapter_4_academic"]
    if transcript_url:
        chapter_4["transcript_provided"] = True
        chapter_4["transcript_image_url"] = transcript_url
    else:
        chapter_4["transcript_provided"] = False
        chapter_4["transcript_image_url"] = ""
    apply_report_quality_gates(report, payload=payload, transcript_url=transcript_url)
    return report


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
        "max_tokens": 16000,
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
    parsed = json.loads(clean_json_text(content))
    return validate_report(parsed)


async def generate_report(
    payload: dict[str, Any],
    *,
    sandplay_image: bytes,
    transcript_image: bytes | None,
    image_url: str,
    transcript_url: str | None,
) -> tuple[dict[str, Any], str]:
    if MULTIMODAL_API_KEY:
        try:
            report = await call_multimodal(payload, sandplay_image, transcript_image, image_url, transcript_url)
            report = normalize_meta(
                report, payload=payload, image_url=image_url, transcript_url=transcript_url,
                engine="multimodal", engine_note="多模态模型生成，经九章节结构校验",
            )
            return report, "multimodal"
        except Exception as exc:  # 生产可改为记录并返回 502；默认允许降级演示报告
            if not ALLOW_DEMO_REPORT:
                raise
            note = f"多模态调用失败，已降级为本地演示报告：{type(exc).__name__}: {exc}"
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
