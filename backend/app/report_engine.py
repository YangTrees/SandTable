from __future__ import annotations

import base64
import json
import re
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
from .theory import CHAPTER_TITLES, RISK_DIMENSIONS, SIX_DIMENSIONS, TRAINING_MODULES
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


def _has_terrain(payload: dict[str, Any]) -> bool:
    return _heightmap_max_abs(payload) > 0.001


def _has_process_data(payload: dict[str, Any]) -> bool:
    summary = payload.get("interaction_summary") or {}
    if not isinstance(summary, dict):
        return False
    process_keys = {
        "duration_seconds", "elapsed_seconds", "total_seconds",
        "drag_count", "delete_count", "undo_count", "undo_steps",
        "brush_strokes", "last_item_dwell_seconds",
    }
    return any(key in summary for key in process_keys)


def _report_basis(payload: dict[str, Any], transcript_url: str | None) -> list[str]:
    items = payload.get("items") or []
    grid = payload.get("grid_distribution") or {}
    basis = ["沙盘作品照片1张"]
    if grid.get("cells"):
        basis.append("九宫格空间分布")
    if items:
        basis.append("沙具使用数据")
    if _has_terrain(payload):
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
        "heightmap_max_abs": round(_heightmap_max_abs(payload), 4),
        "process_data_available": _has_process_data(payload),
        "low_projection": low_projection,
        "label": "低投射量样本" if low_projection else "常规样本",
    }


def _apply_training_gates(report: dict[str, Any], sample_quality: dict[str, Any]) -> None:
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

    ranked: list[tuple[float, int, dict[str, Any]]] = []
    for index, module in enumerate(modules):
        if not isinstance(module, dict):
            continue
        names = [str(name).strip() for name in (module.get("dimensions") or []) if str(name).strip()]
        rank = max((dimension_rank.get(name, 0.0) for name in names), default=0.0)
        name_text = str(module.get("name") or "")
        focus_bonus = 0.25 if any(keyword in name_text for keyword in ("家庭", "情绪", "压力", "睡眠")) else 0.0
        ranked.append((rank + focus_bonus, index, module))

    limit = 2 if sample_quality.get("low_projection") else 3
    active_indices = {
        index for score, index, _ in sorted(ranked, key=lambda item: (-item[0], item[1]))[:limit]
        if score >= 1.5
    }
    if not active_indices and ranked:
        active_indices = {ranked[0][1]}

    for index, module in enumerate(modules):
        if not isinstance(module, dict):
            continue
        active = index in active_indices
        module["active"] = active
        module["status"] = "优先启动" if active else "暂不启动，待信息补充"

    deferred = [str(module.get("name") or "") for index, module in enumerate(modules)
                if isinstance(module, dict) and index not in active_indices]
    chapter["active_count"] = len(active_indices)
    chapter["deferred_modules"] = deferred
    chapter["intro"] = (
        "当前样本投射信息有限，仅启动最相关的优先模块；其余模块待访谈、量表或更充分沙盘信息后再评估。"
        if sample_quality.get("low_projection")
        else "本次优先启动最相关的训练模块，其余模块暂不展开，避免同时增加多项训练负担。"
    )


def _cap_low_sample_confidence(report: dict[str, Any]) -> None:
    """低投射量样本不允许出现“高”置信度，避免用少量沙具做强判断。"""
    for dimension in _chapter_list(report, "chapter_3_six_dimensions", "dimensions"):
        if isinstance(dimension, dict) and str(dimension.get("confidence") or "").strip() == "高":
            dimension["confidence"] = "中"
    for theme in _chapter_list(report, "chapter_2_imagery", "themes"):
        if isinstance(theme, dict) and str(theme.get("confidence") or "").strip() == "高":
            theme["confidence"] = "中"


def _has_cognitive_verification(payload: dict[str, Any], transcript_url: str | None) -> bool:
    """判断认知维度是否有可核对的自述、成绩或教师观察，而不是只有沙盘空间线索。"""
    if transcript_url or str(payload.get("transcript_text") or "").strip():
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


def _apply_theory_guardrails(report: dict[str, Any], payload: dict[str, Any], transcript_url: str | None) -> None:
    """阻断“箱庭空间分布直接推断学科能力”等跨域硬嫁接。

    有自述、成绩或教师观察时，认知维度只写核实路径；没有这些材料时，
    允许保留跨域理论类比，但必须标明为“理论假说·待核实”，不能写成结论。
    """
    has_verification = _has_cognitive_verification(payload, transcript_url)
    for dimension in _chapter_list(report, "chapter_3_six_dimensions", "dimensions"):
        if not isinstance(dimension, dict):
            continue
        key = str(dimension.get("key") or "")
        name = str(dimension.get("name") or "")
        if key != "cognitive" and "认知" not in name:
            continue
        theory = str(dimension.get("assessment_theory") or "").strip()
        cross_domain = "张日昇" in theory and any(
            keyword in theory for keyword in ("认知", "学科", "成绩", "投注", "空间分布", "空间象征")
        )
        if cross_domain and has_verification:
            dimension["assessment_theory"] = (
                "本维度不以箱庭空间分布直接推断学科能力，需结合自述、成绩与教师观察核实。"
            )
        elif cross_domain:
            warning = (
                "【理论假说·待核实】上述跨域理论类比只用于提出假设，"
                "不能由箱庭空间分布直接推断学科能力；需补充受测者自述、成绩与教师观察后再判断。"
            )
            if warning not in theory:
                dimension["assessment_theory"] = theory.rstrip("。") + "。" + warning

        if has_verification:
            for field in ("judgement", "assessment_result", "conclusion"):
                if field in dimension and isinstance(dimension[field], str):
                    dimension[field] = _replace_cognitive_jargon(dimension[field])
            evidence = dimension.get("evidence")
            if isinstance(evidence, list):
                dimension["evidence"] = [
                    _replace_cognitive_jargon(str(item)) if isinstance(item, str) else item
                    for item in evidence
                ]
        else:
            evidence = dimension.get("evidence")
            if isinstance(evidence, list) and not any("理论假说" in str(item) for item in evidence):
                evidence.append("认知相关线索来自箱庭空间分布的理论类比，属待核实假说，不能直接当作学科能力结论。")
    chapter_7 = report.get("chapter_7_career")
    if isinstance(chapter_7, dict):
        if not chapter_7.get("evidence_note"):
            chapter_7["evidence_note"] = (
                "以下优势为基于当前沙盘与自述的探索性假设，不等同于能力测评或稳定人格结论；"
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
        norm = str(dimension.get("norm_reference") or "").strip()
        if (not norm) or ("成绩" in norm) or (
            "量表" in norm and "补" in norm and not any(token in norm for token in ("MHT", "GAD", "PHQ"))
        ):
            dimension["norm_reference"] = (
                "本次无量表数据，为观察性判断，建议补充对应心理量表（如 MHT/GAD-7/PHQ-9）核实"
            )
        if str(dimension.get("level") or "").upper() == "L1" and "未见显性" not in str(dimension.get("judgement") or ""):
            judgement = str(dimension.get("judgement") or "").strip().rstrip("。")
            dimension["judgement"] = (
                (judgement + "；" if judgement else "")
                + "该结论仅基于当前沙盘，未见显性线索不等于无风险，需结合访谈/量表核实。"
            )


def apply_report_quality_gates(
    report: dict[str, Any],
    *,
    payload: dict[str, Any],
    transcript_url: str | None,
) -> dict[str, Any]:
    """服务端质量门控：动态评估依据、低投射量提示、原始记录与训练模块优先级。"""
    meta = report.setdefault("meta", {})
    sample_quality = _sample_quality(payload)
    meta["assessment_basis"] = _report_basis(payload, transcript_url)
    meta["sample_quality"] = sample_quality
    meta["client_inputs"] = {
        "sandplay_description": str(payload.get("sandplay_description") or "").strip(),
        "self_narrative": str(payload.get("self_narrative") or "").strip(),
        "teacher_observation": str(payload.get("teacher_observation") or "").strip(),
        "representative_item_name": str(payload.get("representative_item_name") or "").strip(),
        "interaction_summary": payload.get("interaction_summary") or {},
        "process_note": (
            "已采集制作过程字段，可用于核对操作轨迹。"
            if sample_quality.get("process_data_available")
            else "本次未采集制作耗时、推沙/挖水、修改犹豫次数；仅记录当前交互摘要。"
        ),
    }
    if sample_quality.get("low_projection"):
        _cap_low_sample_confidence(report)
    _apply_training_gates(report, sample_quality)
    _apply_theory_guardrails(report, payload, transcript_url)
    _apply_risk_guardrails(report, sample_quality)
    report["chapter_5_risk"]["visibility"] = "counselor_only"
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
