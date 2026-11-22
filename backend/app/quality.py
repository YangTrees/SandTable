from __future__ import annotations

import re
from collections import Counter
from typing import Any

from .process_metrics import has_process_data


GRID_LABELS = {
    "top_left": "左上",
    "top_center": "上中",
    "top_right": "右上",
    "middle_left": "左中",
    "center": "中心",
    "middle_right": "右中",
    "bottom_left": "左下",
    "bottom_center": "下中",
    "bottom_right": "右下",
    # 兼容前端按左右中三列保存的旧键
    "left": "左侧",
    "right": "右侧",
    "top": "上侧",
    "bottom": "下侧",
}

QUALITY_FLAG_META = {
    "LOW_ITEM_COUNT": ("warning", "低投射量"),
    "SINGLE_CELL_CONCENTRATION": ("warning", "空间高度集中"),
    "HIGH_BLANK_RATIO": ("warning", "大面积留白"),
    "TERRAIN_EVIDENCE_INSUFFICIENT": ("warning", "地形证据不足"),
    "TERRAIN_TEXT_MISMATCH": ("warning", "地形描述与高度图不一致"),
    "GRID_SUMMARY_MISMATCH": ("warning", "九宫格摘要与沙具数据不一致"),
    "EVIDENCE_MISSING": ("warning", "访谈/成绩/过程证据缺失"),
    "EVIDENCE_LIMITED": ("info", "证据有限"),
    "RISK_LEVEL_CONFLICT": ("critical", "顶部预警与风险表不一致"),
    "HOLISTIC_RISK_SYMBOL": ("critical", "整体构图高危文字/符号"),
    "HOLISTIC_SCREEN_UNAVAILABLE": ("critical", "整体构图安全筛查未完成"),
    "TRAINING_INTENSITY_CONFLICT": ("warning", "优先期训练强度不一致"),
    "SCORE_BASIS_MISMATCH": ("warning", "报告引用了不存在的成绩依据"),
    "DEMO_ENGINE": ("info", "示例报告"),
}


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def heightmap_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    heightmap = payload.get("heightmap") if isinstance(payload.get("heightmap"), dict) else {}
    raw_values = heightmap.get("values") if isinstance(heightmap.get("values"), list) else []
    values = [value for value in (_as_float(item) for item in raw_values) if value is not None]
    if not values:
        return {
            "sample_count": 0,
            "nonzero_count": 0,
            "coverage": 0.0,
            "min": 0.0,
            "max": 0.0,
            "max_abs": 0.0,
            "relief": 0.0,
        }
    nonzero_count = sum(1 for value in values if abs(value) > 0.05)
    return {
        "sample_count": len(values),
        "nonzero_count": nonzero_count,
        "coverage": round(nonzero_count / len(values), 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "max_abs": round(max(abs(value) for value in values), 4),
        "relief": round(max(values) - min(values), 4),
    }


def terrain_image_present(payload: dict[str, Any]) -> bool:
    return any(
        bool(payload.get(key))
        for key in ("terrain_image_url", "terrain_image_path", "terrain_heightmap_url", "terrain_map_url")
    )


def terrain_edited(payload: dict[str, Any]) -> bool | None:
    metrics = payload.get("terrain_metrics")
    if not isinstance(metrics, dict) or "terrain_edited" not in metrics:
        return None
    value = metrics.get("terrain_edited")
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "是", "已编辑"}


def _heightmap_is_terrain(height: dict[str, Any]) -> bool:
    """至少两个非零点且有一定覆盖/起伏，避免单个 0.6 采样点翻转样本标签。"""
    if height["nonzero_count"] < 2:
        return False
    if height["max_abs"] < 0.2 or height["relief"] < 0.2:
        return False
    return height["coverage"] >= 0.15 or height["relief"] >= 0.3


def _summary_claims_terrain(summary: str, edited: bool | None) -> bool:
    if edited is True:
        return True
    if not summary:
        return False
    if any(word in summary for word in ("基本平整", "未进行", "未见", "无明显", "没有明显", "无有效")):
        return False
    return any(
        word in summary
        for word in ("地形", "塑形", "水域", "水塘", "湖泊", "河流", "隆起", "沙丘", "沙岛", "高程", "起伏")
    )


def _terrain_mismatch(
    summary: str,
    height: dict[str, Any],
    metrics: dict[str, Any],
    has_terrain: bool,
    edited: bool | None,
) -> bool:
    if not summary:
        return False
    water_pct = _as_float(metrics.get("water_area_pct")) or 0.0
    mound_pct = _as_float(metrics.get("mound_area_pct")) or 0.0
    normalized = summary
    for phrase in (
        "未进行明显地形塑形",
        "未进行地形塑形",
        "未见明显地形塑形",
        "无明显地形塑形",
        "没有明显地形塑形",
        "沙面基本平整",
        "无明显水域",
        "没有明显水域",
        "未见水域",
        "未见隆起",
        "无明显隆起",
        "没有隆起",
    ):
        normalized = normalized.replace(phrase, "")
    water_words = any(word in normalized for word in ("水域", "水塘", "湖泊", "河流", "挖水", "水面"))
    strong_words = any(word in normalized for word in ("明显", "大幅", "大面积", "显著"))
    if water_words and water_pct <= 0:
        return True
    if strong_words and not has_terrain:
        return True
    if mound_pct <= 0 and "隆起" in normalized:
        return True
    if edited is False and height["nonzero_count"] >= 2 and height["max_abs"] >= 0.2:
        return True
    return False


def terrain_observation(payload: dict[str, Any]) -> str:
    metrics = payload.get("terrain_metrics") if isinstance(payload.get("terrain_metrics"), dict) else {}
    summary = str(metrics.get("terrain_summary") or "").strip()
    height = heightmap_metrics(payload)
    edited = terrain_edited(payload)
    image = terrain_image_present(payload)

    if _heightmap_is_terrain(height):
        has_terrain = True
    elif image:
        has_terrain = True
    else:
        has_terrain = False

    mismatch = _terrain_mismatch(summary, height, metrics, has_terrain, edited)
    if mismatch:
        if has_terrain:
            return _supported_terrain_text(metrics, height) + "；客户端地形描述与高度图/量化数据不一致，已以高度图为准。"
        return "沙面基本平整，高度图未见与“明显地形塑形/水域”描述一致的数据；客户端地形描述仅作访谈线索，不写入事实判断。"

    if has_terrain:
        return _supported_terrain_text(metrics, height)
    if height["nonzero_count"]:
        return (
            f"沙面仅见局部起伏（最高 {height['max_abs']:.2f}，起伏 {height['relief']:.2f}，"
            f"非零采样点 {height['nonzero_count']}/{height['sample_count']}），不足以判定明显地形塑形。"
        )
    return "沙面基本平整，未进行明显地形塑形。"


def _supported_terrain_text(metrics: dict[str, Any], height: dict[str, Any]) -> str:
    water = _as_float(metrics.get("water_area_pct")) or 0.0
    mound = _as_float(metrics.get("mound_area_pct")) or 0.0
    relief = _as_float(metrics.get("elevation_range"))
    parts: list[str] = []
    if water > 0:
        parts.append(f"挖出水域约占 {water:.1f}%")
    if mound > 0:
        parts.append(f"隆起沙丘/沙岛约占 {mound:.1f}%")
    if relief is not None and relief > 0:
        parts.append(f"高程差约 {relief:.1f}")
    if height["sample_count"]:
        parts.append(
            f"高度范围 {height['min']:.2f}～{height['max']:.2f}，起伏 {height['relief']:.2f}，"
            f"非零采样点 {height['nonzero_count']}/{height['sample_count']}"
        )
    if parts:
        return "已进行地形塑形：" + "，".join(parts) + "。"
    return "记录为已进行地形塑形，但缺少高度图/水域/隆起量化数据，塑形范围待核验。"


def grid_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    items = [item for item in (payload.get("items") or []) if isinstance(item, dict)]
    grid = payload.get("grid_distribution") if isinstance(payload.get("grid_distribution"), dict) else {}
    cells = [cell for cell in (grid.get("cells") or []) if isinstance(cell, dict)]
    cell_labels = {str(cell.get("key") or ""): str(cell.get("label") or "") for cell in cells}
    summary = grid.get("summary") if isinstance(grid.get("summary"), dict) else {}
    summary_present = any(key in summary for key in ("occupied_cells", "center_count"))
    client_occupied = int(summary.get("occupied_cells") or 0)
    client_center = int(summary.get("center_count") or 0)

    counts: Counter[str] = Counter()
    unknown = 0
    for item in items:
        key = str(item.get("grid_key") or "").strip()
        if not key:
            unknown += 1
            continue
        counts[key] += 1

    if items and (counts or unknown):
        occupied = len(counts) + (1 if unknown else 0)
        center = counts.get("center", 0)
    else:
        occupied = client_occupied
        center = client_center

    max_cell_count = max(counts.values(), default=0)
    blank_cells = max(0, 9 - occupied)
    blank_ratio = round(blank_cells / 9, 4)
    mismatch = bool(items) and (
        unknown > 0
        or (summary_present and (client_occupied != occupied or client_center != center))
    )
    cell_counts = [
        {
            "key": key,
            "label": cell_labels.get(key) or GRID_LABELS.get(key) or key,
            "count": count,
        }
        for key, count in counts.most_common()
    ]
    if unknown:
        cell_counts.append({"key": "unknown", "label": "未定位", "count": unknown})
    return {
        "occupied_cells": occupied,
        "client_occupied_cells": client_occupied,
        "center_count": center,
        "client_center_count": client_center,
        "blank_cells": blank_cells,
        "blank_ratio": blank_ratio,
        "max_cell_count": max_cell_count,
        "cell_counts": cell_counts,
        "grid_mismatch": mismatch,
    }


def _has_scores(payload: dict[str, Any]) -> bool:
    text = str(payload.get("transcript_text") or "")
    if re.search(r"\d+(?:\.\d+)?\s*/\s*\d+(?:\.\d+)?|\d+(?:\.\d+)?\s*分", text):
        return True
    transcript = payload.get("transcript")
    if isinstance(transcript, dict):
        for row in transcript.get("subjects") or []:
            if isinstance(row, dict) and row.get("score") is not None:
                return True
    return False


def _evidence_level(
    *,
    item_count: int,
    low_projection: bool,
    has_narrative: bool,
    has_teacher: bool,
    has_transcript: bool,
    has_scores: bool,
    has_process: bool,
) -> str:
    if has_scores:
        return "adequate"
    if item_count >= 3 and has_narrative and has_teacher:
        return "adequate"
    if low_projection:
        return "minimal"
    if has_narrative or has_teacher or has_transcript or has_process:
        return "limited"
    return "minimal"


def _warning(code: str, message: str, severity: str | None = None) -> dict[str, str]:
    default_severity, _ = QUALITY_FLAG_META.get(code, ("warning", code))
    return {"code": code, "severity": severity or default_severity, "message": message}


def build_sample_quality(payload: dict[str, Any], transcript_url: str | None = None) -> dict[str, Any]:
    items = [item for item in (payload.get("items") or []) if isinstance(item, dict)]
    item_count = len(items)
    height = heightmap_metrics(payload)
    grid = grid_metrics(payload)
    edited = terrain_edited(payload)
    image = terrain_image_present(payload)
    summary = ""
    if isinstance(payload.get("terrain_metrics"), dict):
        summary = str(payload["terrain_metrics"].get("terrain_summary") or "").strip()

    if _heightmap_is_terrain(height):
        has_terrain = True
        terrain_source = "heightmap"
    elif image:
        has_terrain = True
        terrain_source = "image"
    else:
        has_terrain = False
        terrain_source = "client_summary_only" if (summary or edited is not None) else "none"

    mismatch = _terrain_mismatch(
        summary,
        height,
        payload.get("terrain_metrics") if isinstance(payload.get("terrain_metrics"), dict) else {},
        has_terrain,
        edited,
    )
    low_projection = item_count < 3 and not has_terrain

    description = str(payload.get("sandplay_description") or "").strip()
    narrative = str(payload.get("self_narrative") or "").strip()
    teacher = str(payload.get("teacher_observation") or "").strip()
    has_transcript = bool(transcript_url or payload.get("transcript_text") or isinstance(payload.get("transcript"), dict))
    has_scores = _has_scores(payload)
    has_process = has_process_data(payload)

    evidence_level = _evidence_level(
        item_count=item_count,
        low_projection=low_projection,
        has_narrative=bool(narrative),
        has_teacher=bool(teacher),
        has_transcript=has_transcript,
        has_scores=has_scores,
        has_process=has_process,
    )

    flags: list[str] = []
    warnings: list[dict[str, str]] = []
    if item_count < 3:
        flags.append("LOW_ITEM_COUNT")
        terrain_note = (
            "且无有效地形塑形，"
            if low_projection
            else "虽有部分地形/其他线索，"
        )
        warnings.append(_warning(
            "LOW_ITEM_COUNT",
            f"本次仅 {item_count} 件沙具（少于 3 件），{terrain_note}六维与职业建议仅作探索性假设。",
        ))
    if item_count >= 3 and (grid["occupied_cells"] <= 1 or grid["max_cell_count"] / max(item_count, 1) >= 0.8):
        flags.append("SINGLE_CELL_CONCENTRATION")
        share = round(grid["max_cell_count"] / max(item_count, 1) * 100)
        warnings.append(_warning(
            "SINGLE_CELL_CONCENTRATION",
            f"{item_count} 件沙具中有 {grid['max_cell_count']} 件集中在同一格（约 {share}%）；空间分布高度集中，建议核对是否表达受限或摆放受限。",
        ))
    if grid["occupied_cells"] <= 2 or grid["blank_ratio"] >= 0.7:
        flags.append("HIGH_BLANK_RATIO")
        warnings.append(_warning(
            "HIGH_BLANK_RATIO",
            f"画面分区仅占用 {grid['occupied_cells']}/9 格，留白约 {round(grid['blank_ratio'] * 100)}%；大面积留白需结合访谈理解，不宜直接解读为回避。",
        ))
    if (
        height["nonzero_count"] and not has_terrain
    ) or (
        not has_terrain and _summary_claims_terrain(summary, edited)
    ):
        flags.append("TERRAIN_EVIDENCE_INSUFFICIENT")
        if height["nonzero_count"]:
            message = (
                f"高度图仅见局部起伏（最高 {height['max_abs']:.2f}，非零采样点 {height['nonzero_count']}/{height['sample_count']}），不足以判定明显地形塑形，未按地形优势解释。"
            )
        else:
            message = "已有地形描述或编辑记录，但高度图未见足够非零点与起伏，不能把地形当作已成立的优势线索，需结合访谈或补充高度图核验。"
        warnings.append(_warning("TERRAIN_EVIDENCE_INSUFFICIENT", message))
    if mismatch:
        flags.append("TERRAIN_TEXT_MISMATCH")
        warnings.append(_warning(
            "TERRAIN_TEXT_MISMATCH",
            "客户端地形描述与高度图/量化数据不一致；报告已以客观指标为准，地形描述只作访谈线索。",
        ))
    if grid["grid_mismatch"]:
        flags.append("GRID_SUMMARY_MISMATCH")
        warnings.append(_warning(
            "GRID_SUMMARY_MISMATCH",
            f"客户端九宫格摘要（占用 {grid['client_occupied_cells']} 格、中心 {grid['client_center_count']} 件）与沙具实际位置（占用 {grid['occupied_cells']} 格、中心 {grid['center_count']} 件）不一致；报告已按沙具数据重算。",
        ))
    if not (bool(narrative) or bool(teacher) or has_transcript or has_scores or has_process):
        flags.append("EVIDENCE_MISSING")
        warnings.append(_warning(
            "EVIDENCE_MISSING",
            "仅有作品照片/沙具数据，缺少自述、教师观察、成绩或制作过程数据；六维与职业建议只能作为探索性假设，建议补充访谈。",
        ))
    elif evidence_level == "limited":
        flags.append("EVIDENCE_LIMITED")
        warnings.append(_warning(
            "EVIDENCE_LIMITED",
            "已有部分文本线索，但缺少成绩或过程数据；结论置信度应保持在低至中等，并补充访谈核验。",
            severity="info",
        ))

    return {
        "item_count": item_count,
        "occupied_cells": grid["occupied_cells"],
        "client_occupied_cells": grid["client_occupied_cells"],
        "center_count": grid["center_count"],
        "client_center_count": grid["client_center_count"],
        "occupied_cells_ratio": round(grid["occupied_cells"] / 9, 4),
        "blank_cells": grid["blank_cells"],
        "blank_ratio": grid["blank_ratio"],
        "max_cell_count": grid["max_cell_count"],
        "cell_counts": grid["cell_counts"],
        "grid_mismatch": grid["grid_mismatch"],
        "has_terrain": has_terrain,
        "terrain_edited": edited,
        "terrain_image": image,
        "terrain_source": terrain_source,
        "terrain_summary": terrain_observation(payload),
        "client_terrain_summary": summary,
        "terrain_text_mismatch": mismatch,
        "heightmap_max_abs": height["max_abs"],
        "heightmap_coverage": height["coverage"],
        "heightmap_nonzero_count": height["nonzero_count"],
        "heightmap_sample_count": height["sample_count"],
        "heightmap_min": height["min"],
        "heightmap_max": height["max"],
        "heightmap_relief": height["relief"],
        "has_description": bool(description),
        "has_narrative": bool(narrative),
        "has_teacher": bool(teacher),
        "has_transcript": has_transcript,
        "has_scores": has_scores,
        "process_data_available": has_process,
        "evidence_level": evidence_level,
        "low_projection": low_projection,
        "label": "低投射量样本" if low_projection else ("样本量有限" if item_count < 3 else "常规样本"),
        "quality_flags": flags,
        "quality_warnings": warnings,
    }


def build_assessment_basis(payload: dict[str, Any], transcript_url: str | None = None) -> list[str]:
    quality = build_sample_quality(payload, transcript_url)
    items = payload.get("items") or []
    basis = ["沙盘作品照片1张"]
    if items or quality["occupied_cells"]:
        basis.append("九宫格空间分布")
    if items:
        basis.append("沙具使用数据")
    if quality["heightmap_sample_count"]:
        if quality["has_terrain"]:
            basis.append("沙盘地形高度图")
        elif quality["heightmap_nonzero_count"]:
            basis.append("沙盘高度图（仅见局部起伏）")
        else:
            basis.append("沙盘高度图（未见有效起伏）")
    elif quality["terrain_image"]:
        basis.append("沙盘地形图")
    elif quality["terrain_edited"] is True or quality["client_terrain_summary"]:
        basis.append("沙盘地形记录（仅客户端声明，未采用）")
    if payload.get("representative_item_id") or payload.get("representative_item_name"):
        basis.append("代表沙具1件")
    if quality["has_description"]:
        basis.append("受测者沙盘描述1段")
    if quality["has_narrative"]:
        basis.append("受测者自述文本")
    if quality["has_teacher"]:
        basis.append("教师观察记录")
    if quality["process_data_available"]:
        basis.append("制作过程操作数据")
    if transcript_url:
        basis.append("学习成绩单1张")
    return basis
