from __future__ import annotations

import re
from typing import Any

HOLISTIC_SCREEN_PROMPT = """你是沙盘作品安全筛查器。只看沙盘整体构图，不要只看单个沙具，也不要把“单个沙具正常”当成“整体安全”。
任务：
1. 先看沙面、水域、沙丘、沙具排列和留白共同构成了什么整体图形、文字或符号；描述轮廓，再逐字转录所有清晰可读的汉字、字母、数字或符号。
2. 判断这些整体符号可能在表达什么，是否出现死亡、自杀、绝望、告别、威胁、求救等高风险语义。
3. 必须区分“单个沙具含义”和“整体构图含义”；单个沙具正常不能抵消整体高危文字。
4. 只有轮廓完整、无须猜测就能独立读出的单字/词才写入 readable_text；笔画残缺、需要脑补时写空数组，risk_level 不得为 high。不要为了寻找风险把随机水迹强行解释成字。
5. 如果整体构图形成“死”“亡”“自杀”“绝”“杀”“丧”“葬”“墓”“SOS”“求救”等字词，risk_level 必须为 high。
只返回 JSON，不要解释：
{"overall_forms":["..."],"readable_text":["..."],"symbol_meaning":"...","risk_level":"none|watch|high","risk_evidence":"...","confidence":"high|medium|low"}"""

HIGH_RISK_VISUAL_TERMS = (
    "自杀",
    "去死",
    "想死",
    "寻死",
    "死亡",
    "死",
    "亡",
    "绝",
    "杀",
    "丧",
    "葬",
    "墓",
    "诀别",
    "永别",
    "SOS",
    "求救",
    "救命",
)


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item or "").strip()]
    text = str(value or "").strip()
    return [text] if text else []


def _normalize_level(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"high", "critical", "高风险", "高危", "高"}:
        return "high"
    if text in {"watch", "medium", "关注", "中"}:
        return "watch"
    if text in {"none", "low", "无", "低"}:
        return "none"
    return text or "unknown"


def normalize_screen(raw: dict[str, Any] | None, *, status: str = "ok") -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    return {
        "status": status,
        "overall_forms": _as_list(source.get("overall_forms"))[:8],
        "readable_text": _as_list(source.get("readable_text"))[:12],
        "symbol_meaning": str(source.get("symbol_meaning") or "").strip(),
        "risk_level": _normalize_level(source.get("risk_level")),
        "risk_evidence": str(source.get("risk_evidence") or "").strip(),
        "confidence": str(source.get("confidence") or "").strip() or "unknown",
    }


def _screen_text(screen: dict[str, Any]) -> str:
    fields = []
    for key in ("readable_text", "overall_forms", "symbol_meaning", "risk_evidence"):
        value = screen.get(key)
        if isinstance(value, list):
            fields.extend(str(item) for item in value)
        else:
            fields.append(str(value or ""))
    return " ".join(fields)


def matched_high_risk_terms(screen: dict[str, Any]) -> list[str]:
    """只匹配模型明确转录出的整体文字，避免把“未见死亡”这类否定描述误判为高危。"""
    text = " ".join(_as_list(screen.get("readable_text")))
    normalized = re.sub(r"\s+", "", text).upper()
    hits = [term for term in HIGH_RISK_VISUAL_TERMS if term.upper() in normalized]
    return sorted(set(hits), key=lambda item: (-len(item), item))


def is_high_risk(screen: dict[str, Any] | None) -> bool:
    if not isinstance(screen, dict):
        return False
    if _normalize_level(screen.get("risk_level")) == "high":
        return True
    return bool(matched_high_risk_terms(screen))


def screen_triggers(screen: dict[str, Any] | None) -> list[str]:
    if not isinstance(screen, dict):
        return []
    if screen.get("status") == "failed":
        return ["整体构图安全筛查未完成：需人工复核整体画面"]
    if not is_high_risk(screen):
        return []
    generic = "整体构图出现需专业核查的高危文字或符号"
    text = "、".join(_as_list(screen.get("readable_text"))[:4]).strip()
    if text:
        return [f"整体构图高危文字：{text}（{generic}）"]
    forms = "、".join(_as_list(screen.get("overall_forms"))[:2]).strip()
    if forms:
        return [f"整体构图高危符号：{forms}（{generic}）"]
    return [f"{generic}：筛查判定 high"]


def prompt_context(screen: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(screen, dict):
        return {"status": "not_run"}
    return {
        "status": screen.get("status") or "unknown",
        "overall_forms": screen.get("overall_forms") or [],
        "readable_text": screen.get("readable_text") or [],
        "symbol_meaning": screen.get("symbol_meaning") or "",
        "risk_level": screen.get("risk_level") or "unknown",
        "risk_evidence": screen.get("risk_evidence") or "",
        "confidence": screen.get("confidence") or "unknown",
    }
