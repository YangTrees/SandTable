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
    data.pop("chapter_5_risk", None)
    data.pop("counselor_only", None)
    data.pop("risk_level", None)
    data.pop("risk_summary", None)
    data.get("meta", {}).pop("counselor_note", None)
    data.get("meta", {}).pop("review_note", None)
    data.get("meta", {}).pop("client_inputs", None)
    data = _public_scrub(data)
    data["share_visibility"] = "student_guardian"
    data["redacted_chapters"] = ["chapter_5_risk"]
    return data
