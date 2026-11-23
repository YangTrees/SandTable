from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from datetime import datetime, timezone
from typing import Any

from .config import MEDIA_SIGNED_URL_TTL_SECONDS, MEDIA_SIGNING_SECRET


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


_MEDIA_URL_RE = re.compile(r"(/media/([A-Za-z0-9_-]+)/([A-Za-z0-9_.-]+))(?:\?[^\s\"'<>]*)?")
_MEDIA_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_MEDIA_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def media_signature(assessment_id: str, filename: str, expires: int) -> str:
    message = f"{assessment_id}/{filename}:{expires}".encode("utf-8")
    digest = hmac.new(MEDIA_SIGNING_SECRET.encode("utf-8"), message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def signed_media_url(base_url: str, assessment_id: str, filename: str) -> str:
    if not _MEDIA_ID_RE.fullmatch(str(assessment_id)) or not _MEDIA_NAME_RE.fullmatch(str(filename)):
        return ""
    expires = int(time.time()) + max(60, MEDIA_SIGNED_URL_TTL_SECONDS)
    signature = media_signature(assessment_id, filename, expires)
    return f"{base_url.rstrip('/')}/media/{assessment_id}/{filename}?exp={expires}&sig={signature}"


def sign_report_media(value: Any, assessment_id: str) -> Any:
    """给报告中的沙盘图 / 成绩单地址追加短期签名，避免公开静态目录被枚举。"""
    if isinstance(value, dict):
        return {key: sign_report_media(item, assessment_id) for key, item in value.items()}
    if isinstance(value, list):
        return [sign_report_media(item, assessment_id) for item in value]
    if isinstance(value, str):
        def replace(match: re.Match[str]) -> str:
            path, owner, filename = match.group(1), match.group(2), match.group(3)
            if owner != assessment_id:
                return match.group(0)
            expires = int(time.time()) + max(60, MEDIA_SIGNED_URL_TTL_SECONDS)
            signature = media_signature(owner, filename, expires)
            return f"{path}?exp={expires}&sig={signature}"

        return _MEDIA_URL_RE.sub(replace, value)
    return value


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


def parse_json_object(text: str) -> Any:
    """解析模型返回的 JSON 对象，忽略对象结束后的附加说明或第二段内容。"""
    cleaned = clean_json_text(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        if start < 0:
            raise
        value, _ = json.JSONDecoder().raw_decode(cleaned, start)
        return value


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
            if lowered.startswith("counselor") or lowered in {"risk_level", "risk_summary", "risk_overview"}:
                continue
            out[key] = _public_scrub(item)
        return out
    if isinstance(value, list):
        return [_public_scrub(item) for item in value]
    if isinstance(value, str):
        return (
            value.replace("九宫格", "画面分区")
            .replace("宫格", "区域")
            .replace("风险分级", "评估结果")
            .replace("风险等级", "评估结果")
        )
    return value


def public_copy(report: dict[str, Any]) -> dict[str, Any]:
    """家长/学生端序列化层：强制剔除第五章及咨询师内部字段。"""
    import copy

    data = copy.deepcopy(report)
    banner = data.get("priority_banner") or {}
    level = str(banner.get("level") or "").upper()
    l4_guard = "L4" in level
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    holistic_high = str(meta.get("holistic_screen_risk") or "").lower() == "high"
    data.pop("chapter_5_risk", None)
    data.pop("counselor_only", None)
    data.pop("risk_level", None)
    data.pop("risk_summary", None)
    data.pop("priority_banner", None)
    data.pop("risk_banner", None)
    data.pop("raw_record_echo", None)
    data.pop("longitudinal_comparison", None)
    summary_card = data.get("summary_card")
    if isinstance(summary_card, dict):
        public_summary = summary_card.get("public")
        if isinstance(public_summary, dict):
            data["summary_card"] = _public_scrub(public_summary)
        else:
            data.pop("summary_card", None)
    else:
        data.pop("summary_card", None)
    if isinstance(meta, dict):
        meta.pop("counselor_note", None)
        meta.pop("review_note", None)
        meta.pop("client_inputs", None)
        meta.pop("holistic_screen", None)
        meta.pop("holistic_screen_risk", None)
        meta.pop("previous_assessment", None)
        public_meta_blocked_prefixes = (
            "student_", "school_", "class_", "teacher_", "guardian_",
            "heightmap_", "terrain_", "sample_", "client_", "generation_",
            "counselor_", "risk_",
        )
        public_meta_blocked_keys = {
            "self_image", "self_image_note", "engine", "engine_note",
            "quality_flags", "quality_warnings", "quality_level", "process_metrics",
            "school", "class_name", "phone", "email", "account", "user_id",
        }
        for key in list(meta.keys()):
            lowered = str(key).lower()
            if lowered in public_meta_blocked_keys or lowered.startswith(public_meta_blocked_prefixes):
                meta.pop(key, None)
    chapter1 = data.get("chapter_1_overview")
    if isinstance(chapter1, dict):
        chapter1.pop("process_observation", None)
        chapter1.pop("holistic_visual_check", None)
        if holistic_high:
            for field in ("clusters", "blank_areas", "scene_imagery"):
                value = chapter1.get(field)
                if isinstance(value, list):
                    chapter1[field] = [
                        "整体构图出现需专业核查的高危文字/符号" if any(
                            term in str(item) for term in ("死", "自杀", "诀别", "永别", "SOS", "求救", "救命")
                        ) else item
                        for item in value
                    ]
                elif isinstance(value, str) and any(
                    term in value for term in ("死", "自杀", "诀别", "永别", "SOS", "求救", "救命")
                ):
                    chapter1[field] = "整体构图出现需专业核查的高危文字/符号"
    if l4_guard:
        chapter8 = data.get("chapter_8_training_modules")
        if isinstance(chapter8, dict):
            chapter8["intro"] = "本阶段训练模块暂缓，具体安排以心理老师的沟通为准。"
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
