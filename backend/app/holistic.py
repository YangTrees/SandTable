from __future__ import annotations

import re
from typing import Any

HOLISTIC_SCREEN_PROMPT = """你是沙盘作品安全筛查器。只看沙盘整体构图和清晰可辨的高危物体，不要只看单个沙具，也不要把“单个沙具正常”当成“整体安全”。
任务：
1. 先看沙面、水域、沙丘、沙具排列和留白共同构成了什么整体图形、文字或符号；描述轮廓，再逐字转录所有清晰可读的汉字、字母、数字或符号。
2. 判断这些整体符号可能在表达什么，是否出现死亡、自杀、绝望、告别、威胁、求救等高风险语义。
3. 必须区分“单个沙具含义”和“整体构图含义”；单个沙具正常不能抵消整体高危文字。
4. 只有轮廓完整、无须猜测就能独立读出的单字/词才写入 readable_text；笔画残缺、需要脑补时写空数组，risk_level 不得为 high。不要为了寻找风险把随机水迹强行解释成字。
5. 如果整体构图形成“死”“亡”“自杀”“绝”“杀”“丧”“葬”“墓”“SOS”“求救”等字词，risk_level 必须为 high。
6. 单独筛查清晰可见的视觉高危物体：枪械、刀具/匕首、爆炸物、尸体/倒地人形、排泄物、血液、开放性伤口、上吊/悬吊。只记录能明确辨认的实体，不凭阴影、颜色、远景模糊形状猜测；看不清就不写。
7. 每个视觉物体必须给出位置、朝向、与人物关系、场景语境和 severity。判定规则：
   - high：枪口/刀尖明确指向人物；武器压在/贴近倒地人形；尸体或倒地无反应人形；血液/开放性伤口出现在人物身上；上吊/悬吊；排泄物涂抹在人物、食物或仪式化摆放。
   - watch：武器出现在军事、警察、博物馆、玩具或陈列场景，且没有指向人物、没有冲突动作；排泄物在厕所/马桶/卫生场景；血迹/伤口在医疗场景；无法判断是否指向人物或与人物有关。
   - none：普通卫生设施、装饰性武器、玩具士兵，且无人物冲突或伤害关系。
   - 不能因为“出现一把枪”就判定敌对或高危；必须看枪口朝向、与人物关系、场景语境。单个 high 物体也不自动等于 L4，由服务端结合死亡符号、数量、文本和制作过程决定。
8. visual_risk_level 取所有 visual_risk_objects 中的最高 severity；没有高危物体时可为 none 或 watch。
只返回 JSON，不要解释：
{"overall_forms":["..."],"readable_text":["..."],"symbol_meaning":"...","risk_level":"none|watch|high","risk_evidence":"...","visual_risk_objects":[{"type":"firearm|knife|explosive|corpse|excrement|blood|wound|hanging|other","label":"...","location":"...","orientation":"...","person_relation":"...","scene_context":"...","severity":"none|watch|high","evidence":"..."}],"visual_risk_level":"none|watch|high","visual_risk_summary":"...","confidence":"high|medium|low"}"""

VISUAL_RISK_TYPES = {
    "firearm", "knife", "explosive", "corpse", "excrement",
    "blood", "wound", "hanging", "other",
}
VISUAL_RISK_TYPE_LABELS = {
    "firearm": "枪械",
    "knife": "刀具",
    "explosive": "爆炸物",
    "corpse": "尸体/倒地人形",
    "excrement": "排泄物",
    "blood": "血液",
    "wound": "开放性伤口",
    "hanging": "上吊/悬吊",
    "other": "其他高危物体",
}


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


def _normalize_visual_objects(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, str]] = []
    for item in value[:10]:
        if not isinstance(item, dict):
            continue
        risk_type = str(item.get("type") or "other").strip().lower()
        if risk_type not in VISUAL_RISK_TYPES:
            risk_type = "other"
        severity = _normalize_level(item.get("severity"))
        if severity not in {"none", "watch", "high"}:
            severity = "watch"
        label = str(item.get("label") or "").strip() or VISUAL_RISK_TYPE_LABELS[risk_type]
        rows.append({
            "type": risk_type,
            "type_label": VISUAL_RISK_TYPE_LABELS[risk_type],
            "label": label[:80],
            "location": str(item.get("location") or "").strip()[:120],
            "orientation": str(item.get("orientation") or "").strip()[:120],
            "person_relation": str(item.get("person_relation") or "").strip()[:160],
            "scene_context": str(item.get("scene_context") or "").strip()[:160],
            "severity": severity,
            "evidence": str(item.get("evidence") or "").strip()[:300],
        })
    return rows


def _highest_visual_level(objects: list[dict[str, str]]) -> str:
    levels = [str(item.get("severity") or "") for item in objects]
    if "high" in levels:
        return "high"
    if "watch" in levels:
        return "watch"
    if levels:
        return "none"
    return "none"


def normalize_screen(raw: dict[str, Any] | None, *, status: str = "ok") -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    visual_objects = _normalize_visual_objects(source.get("visual_risk_objects"))
    declared_visual_level = _normalize_level(source.get("visual_risk_level"))
    visual_level = _highest_visual_level(visual_objects)
    if declared_visual_level in {"high", "watch", "none"}:
        rank = {"none": 1, "watch": 2, "high": 3}
        visual_level = declared_visual_level if rank[declared_visual_level] >= rank[visual_level] else visual_level
    return {
        "status": status,
        "overall_forms": _as_list(source.get("overall_forms"))[:8],
        "readable_text": _as_list(source.get("readable_text"))[:12],
        "symbol_meaning": str(source.get("symbol_meaning") or "").strip(),
        "risk_level": _normalize_level(source.get("risk_level")),
        "risk_evidence": str(source.get("risk_evidence") or "").strip(),
        "visual_risk_objects": visual_objects,
        "visual_risk_level": visual_level,
        "visual_risk_summary": str(source.get("visual_risk_summary") or "").strip()[:500],
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


def visual_high_objects(screen: dict[str, Any] | None) -> list[dict[str, str]]:
    if not isinstance(screen, dict):
        return []
    return [
        item for item in (screen.get("visual_risk_objects") or [])
        if isinstance(item, dict) and str(item.get("severity") or "").lower() == "high"
    ]


def visual_watch_objects(screen: dict[str, Any] | None) -> list[dict[str, str]]:
    if not isinstance(screen, dict):
        return []
    return [
        item for item in (screen.get("visual_risk_objects") or [])
        if isinstance(item, dict) and str(item.get("severity") or "").lower() == "watch"
    ]


def _visual_object_phrase(item: dict[str, Any]) -> str:
    label = str(item.get("label") or item.get("type_label") or "高危物体").strip()
    parts = [
        str(item.get(field) or "").strip()
        for field in ("location", "orientation", "person_relation", "scene_context")
    ]
    detail = "，".join(part for part in parts if part)
    return f"视觉高危物体：{label}{f'（{detail}）' if detail else ''}"


def visual_risk_triggers(screen: dict[str, Any] | None) -> list[str]:
    """只输出达到 high 的视觉物体；watch 只进观察记录，不自动抬升优先级。"""
    objects = visual_high_objects(screen)
    return [_visual_object_phrase(item) for item in objects[:4]]


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
        "visual_risk_objects": screen.get("visual_risk_objects") or [],
        "visual_risk_level": screen.get("visual_risk_level") or "unknown",
        "visual_risk_summary": screen.get("visual_risk_summary") or "",
        "confidence": screen.get("confidence") or "unknown",
    }
