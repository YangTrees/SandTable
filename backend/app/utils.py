from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone
from typing import Any


def new_id(prefix: str = "") -> str:
    return f"{prefix}{secrets.token_hex(8)}"


def new_share_token() -> str:
    return secrets.token_urlsafe(32)


def iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def clean_json_text(text: str) -> str:
    """容忍模型返回的 Markdown 代码围栏。"""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text


def report_chapter_count(report: dict[str, Any]) -> int:
    return sum(1 for key in report if re.fullmatch(r"chapter_[1-9]_[a-z_]+", key))


def _public_scrub(value: Any) -> Any:
    """Recursively remove counselor-only payloads and algorithm-facing wording."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in {"nine_grid_distribution", "grid_distribution", "heightmap"}:
                continue
            if lowered.startswith("counselor") or lowered in {"risk_level", "risk_summary"}:
                continue
            out[key] = _public_scrub(item)
        return out
    if isinstance(value, list):
        return [_public_scrub(item) for item in value]
    if isinstance(value, str):
        return value.replace("九宫格", "画面分区").replace("宫格", "区域")
    return value


def public_copy(report: dict[str, Any]) -> dict[str, Any]:
    """家长/学生端序列化层：强制剔除第五章及咨询师内部字段。"""
    import copy

    data = copy.deepcopy(report)
    banner = data.get("priority_banner") or {}
    level = str(banner.get("level") or "").upper()
    l4_guard = "L4" in level
    data.pop("chapter_5_risk", None)
    data.pop("counselor_only", None)
    data.pop("risk_level", None)
    data.pop("risk_summary", None)
    data.pop("priority_banner", None)
    data.pop("risk_banner", None)
    data.pop("raw_record_echo", None)
    meta = data.get("meta")
    if isinstance(meta, dict):
        meta.pop("counselor_note", None)
        meta.pop("review_note", None)
        meta.pop("client_inputs", None)
    chapter1 = data.get("chapter_1_overview")
    if isinstance(chapter1, dict):
        chapter1.pop("process_observation", None)
    data = _public_scrub(data)
    if l4_guard:
        data["share_guard"] = {
            "blocked": False,
            "title": "建议家长先与心理老师沟通",
            "message": (
                "本报告为发展性评估参考。建议家长先联系学校心理老师沟通后再解读；"
                "如报告涉及需要优先关注的线索，心理老师会按学校流程单独与家长沟通。"
            ),
            "note": "家长版已隐藏咨询师内部研判与风险分级，仅保留发展性建议。",
        }
    data["share_visibility"] = "student_guardian"
    data["redacted_chapters"] = ["chapter_5_risk", "priority_banner"]
    return data
