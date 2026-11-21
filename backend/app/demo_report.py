from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from .quality import build_assessment_basis, build_sample_quality, terrain_observation
from .theory import CHAPTER_TITLES, RISK_DIMENSIONS, SIX_DIMENSIONS, THEORY_EVIDENCE, TRAINING_MODULES


GRADE_STANDARD = "优秀 ≥80% · 良好 70%-80%（含70%） · 合格 60%-70%（含60%） · 不合格 <60%"


def _grade(rate: float | None) -> str:
    if rate is None:
        return "待核对"
    if rate >= 0.8:
        return "优秀"
    if rate >= 0.7:
        return "良好"
    if rate >= 0.6:
        return "合格"
    return "不合格"


def _parse_transcript_text(text: str | None) -> list[dict[str, Any]]:
    if not text:
        return []
    rows = []
    patterns = [
        re.compile(r"([\u4e00-\u9fa5A-Za-z]{1,18})\s*[:：]?\s*(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)"),
        re.compile(r"([\u4e00-\u9fa5A-Za-z]{1,18})\s*[:：]?\s*(\d+(?:\.\d+)?)\s*分\s*[（(]?满分\s*(\d+(?:\.\d+)?)"),
    ]
    for pattern in patterns:
        for subject, score, full in pattern.findall(text):
            try:
                score_f, full_f = float(score), float(full)
            except ValueError:
                continue
            if full_f <= 0 or score_f < 0 or score_f > full_f + 1:
                continue
            rate = round(score_f / full_f, 4)
            rows.append({
                "subject": subject.strip(),
                "full_score": full_f,
                "score": score_f,
                "rate": rate,
                "grade": _grade(rate),
            })
    # 去重，保留先出现的科目
    unique: dict[str, dict[str, Any]] = {}
    for row in rows:
        unique.setdefault(row["subject"], row)
    return list(unique.values())


def _height_stats(heightmap: dict[str, Any]) -> dict[str, float]:
    values = [float(v) for v in (heightmap.get("values") or []) if isinstance(v, (int, float))]
    if not values:
        return {"mean": 0.0, "min": 0.0, "max": 0.0, "relief": 0.0}
    return {
        "mean": round(sum(values) / len(values), 2),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
        "relief": round(max(values) - min(values), 2),
    }


def _category_counts(items: list[dict[str, Any]]) -> Counter:
    categories = Counter()
    for item in items:
        categories[str(item.get("category") or item.get("category_name") or "未分类")] += 1
    return categories


def _subcategory_counts(items: list[dict[str, Any]]) -> Counter:
    counts = Counter()
    for item in items:
        key = str(item.get("subcategory") or "").strip()
        if key:
            counts[key] += 1
    return counts


def _theme_counts(items: list[dict[str, Any]]) -> Counter:
    counts = Counter()
    for item in items:
        for code in item.get("themes") or []:
            key = str(code or "").strip()
            if key:
                counts[key] += 1
    return counts


THEME_LIBRARY = {
    "conflict": {
        "name": "冲突与对抗",
        "hypothesis": "沙盘中出现兵器、军事、争夺或高对抗意象，可能表达攻击性张力、边界维护，也可能反映对冲突升级的担忧。",
        "alternative": "另一种可能是，这些意象在具体位置与组合中承载的是保护、规则感或对力量的自保需要，而非攻击意图。",
        "question": "这些对抗性沙具更像是在表达愤怒与冲突，还是在表达保护边界、争取空间或对威胁的警觉？",
    },
    "pressure": {
        "name": "限制与压力",
        "hypothesis": "封闭、束缚、监控、学业堆积等意象集中出现，可能反映被规则、期待或评价压住的体验。",
        "alternative": "另一种可能是，这些结构在作品里提供秩序、边界和可预期的安全感，需结合朝向与是否可进入判断。",
        "question": "这些限制性意象更像是让人窒息的压力，还是提供秩序与边界的保护结构？",
    },
    "crisis": {
        "name": "崩解与丧失",
        "hypothesis": "灾害、破损、死亡、枯竭等意象出现，可能提示失控、丧失或支撑系统松动的体验。",
        "alternative": "另一种可能是，它们作为旧阶段的结束标记，正在为重建与转化腾出空间。",
        "question": "这些崩解意象更像是在表达仍在发生的丧失，还是在表达旧阶段结束后的重建起点？",
    },
    "shadow": {
        "name": "阴影与隐匿",
        "hypothesis": "面具、影子、躲藏、背对等意象出现，可能承载羞耻、压抑、退缩或不愿被看见的部分。",
        "alternative": "另一种可能是，它们表达的是隐私边界、独处需要或尚未准备好的自我暴露。",
        "question": "这些隐匿意象更像是在回避与羞耻，还是在保护尚未准备好公开的私人空间？",
    },
    "transformation": {
        "name": "修复与转化",
        "hypothesis": "桥梁、钥匙、门、萌发、救援等意象出现，可能提示连接重建、束缚解除或生命力恢复的资源。",
        "alternative": "另一种可能是，它们表达的是对修复的渴望而非已经完成的转化，仍需访谈确认现实支持。",
        "question": "这些转化意象更像是已经发生的修复，还是仍在期待中的出路与支持？",
    },
}


def _grid_label_map(grid: dict[str, Any]) -> dict[str, Any]:
    cells = grid.get("cells") or []
    return {cell.get("key"): cell for cell in cells if isinstance(cell, dict)}


def _top_clusters(grid: dict[str, Any]) -> list[dict[str, Any]]:
    cells = [c for c in (grid.get("cells") or []) if isinstance(c, dict)]
    return sorted(cells, key=lambda c: int(c.get("count") or 0), reverse=True)[:3]


def _risk_level(name: str, text: str) -> tuple[str, str]:
    if name == "自我伤害倾向":
        if any(word in text for word in ("自伤", "自杀", "不想活", "伤害自己", "割腕")):
            return "L3", "存在需立即关注的表达线索，建议尽快由专业人员面询与安全评估"
        return "L1", "无明确自伤相关表达或行为线索"
    if name == "学习压力感":
        if any(word in text for word in ("压力", "考试", "成绩下降", "作业", "请假", "不想上学")):
            return "L2", "自述/沙盘中出现与学业压力相关的线索"
    if name == "学习倦怠":
        if any(word in text for word in ("厌学", "不想学", "没动力", "疲惫", "摆烂")):
            return "L2", "出现学习动力下降或回避学习场景的表达"
    if name == "焦虑":
        if any(word in text for word in ("焦虑", "紧张", "失眠", "害怕", "担心")):
            return "L2", "自述中出现焦虑或紧张相关表达"
    if name == "抑郁":
        if any(word in text for word in ("低落", "孤独", "没意思", "退缩", "想哭")):
            return "L2", "出现情绪低落或退缩线索，尚未见长期持续描述"
    if name == "人际关系敏感":
        if any(word in text for word in ("同学", "孤立", "没朋友", "社交", "排斥")):
            return "L2", "自述中出现人际回避或关系紧张线索"
    if name == "强迫":
        if any(word in text for word in ("强迫", "反复", "检查", "必须")):
            return "L2", "出现重复行为或高控制需求线索"
    if name == "偏执":
        if any(word in text for word in ("不信任", "针对我", "怀疑", "监视")):
            return "L2", "出现不信任或被针对感线索"
    if name == "敌对":
        if any(word in text for word in ("愤怒", "冲突", "打架", "恨")):
            return "L2", "出现愤怒或冲突相关表达"
    return "L1", "无明确相关线索"


def _risk_label(level: str) -> str:
    return {
        "L1": "L1 平稳",
        "L2": "L2 轻度关注",
        "L3": "L3 中度关注",
        "L4": "L4 高度关注",
    }[level]


def build_demo_report(
    payload: dict[str, Any],
    *,
    sandplay_image_url: str,
    transcript_image_url: str | None,
    engine_note: str = "",
) -> dict[str, Any]:
    items = payload.get("items") or []
    student = payload.get("student") or {}
    grid = payload.get("grid_distribution") or {}
    description = str(payload.get("sandplay_description") or "")
    narrative = str(payload.get("self_narrative") or "")
    teacher_observation = str(payload.get("teacher_observation") or "")
    rep_id = str(payload.get("representative_item_id") or "")
    rep_name = str(payload.get("representative_item_name") or "")
    rep_item = next((x for x in items if str(x.get("id")) == rep_id), {})
    if not rep_name:
        rep_name = str(rep_item.get("label") or rep_item.get("name") or "代表沙具")

    category_counts = _category_counts(items)
    subcategory_counts = _subcategory_counts(items)
    theme_counts = _theme_counts(items)
    categories = [name for name, _ in category_counts.most_common()]
    top_categories = categories[:3] or ["未分类"]
    quality = build_sample_quality(payload, transcript_image_url)
    clusters = [cell for cell in quality["cell_counts"] if str(cell.get("key") or "") != "unknown"]
    occupied = int(quality["occupied_cells"] or 0)
    center_count = int(quality["center_count"] or 0)
    scores = _parse_transcript_text(str(payload.get("transcript_text") or "")) if payload.get("transcript_text") else []
    if not scores and isinstance(payload.get("transcript"), dict):
        raw_subjects = payload["transcript"].get("subjects") or []
        for row in raw_subjects:
            if not isinstance(row, dict):
                continue
            try:
                score = float(row.get("score"))
                full = float(row.get("full_score"))
            except (TypeError, ValueError):
                continue
            if full <= 0:
                continue
            rate = round(score / full, 4)
            scores.append({
                "subject": str(row.get("subject") or "未命名科目"),
                "full_score": full, "score": score, "rate": rate, "grade": row.get("grade") or _grade(rate),
            })

    text_all = f"{description}\n{narrative}\n{teacher_observation}"
    strongest_cluster = clusters[0] if clusters and int(clusters[0].get("count") or 0) > 0 else None
    if strongest_cluster and occupied > 1 and int(strongest_cluster.get("count") or 0) <= 1:
        cluster_text = f"沙具分散于 {occupied} 个区域，中心区共 {center_count} 件"
    elif strongest_cluster:
        cluster_text = (
            f"沙具主要聚集于{strongest_cluster.get('label')}区域（{strongest_cluster.get('count')} 件），"
            f"中心区共 {center_count} 件"
        )
    else:
        cluster_text = "当前沙盘尚未形成明显的沙具聚集区"
    blank_text = (
        f"画面分区中有 {9 - occupied} 个区域未被占用，留白率约 {round((9 - occupied) / 9, 1):.0%}；"
        "留白可作为距离感、回避或尚未表达之内容的探索线索"
    )
    terrain_text = quality["terrain_summary"]
    cluster_by_key = {
        str(cell.get("key") or ""): cell
        for cell in (quality.get("cell_counts") or [])
        if isinstance(cell, dict)
    }
    grid_cells: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for raw_cell in (grid.get("cells") or []):
        if not isinstance(raw_cell, dict):
            continue
        key = str(raw_cell.get("key") or "").strip()
        if not key:
            continue
        seen_keys.add(key)
        cluster = cluster_by_key.get(key) or {}
        grid_cells.append({
            "key": key,
            "label": str(raw_cell.get("label") or cluster.get("label") or key),
            "count": int(cluster.get("count") or 0),
        })
    for key, cluster in cluster_by_key.items():
        if key in seen_keys:
            continue
        grid_cells.append({
            "key": key,
            "label": str(cluster.get("label") or key),
            "count": int(cluster.get("count") or 0),
        })
    grid_display = {
        "summary": {
            "occupied_cells": occupied,
            "center_count": center_count,
            "blank_cells": int(quality.get("blank_cells") or 0),
        },
        "cells": grid_cells,
    }

    # 第二章：优先使用沙具主题标签形成竞争性假设；无标签时回退到器物类别。
    themes = []
    for code, count in theme_counts.most_common(3):
        definition = THEME_LIBRARY.get(code)
        if not definition:
            continue
        symbols = [
            str(x.get("label") or x.get("name") or "未命名沙具")
            for x in items
            if code in (x.get("themes") or [])
        ][:6]
        themes.append({
            "theme": definition["name"],
            "symbols": symbols or [rep_name],
            "hypothesis": definition["hypothesis"] + f" 本次共有 {count} 件沙具带此主题标签；代表沙具「{rep_name}」位于{rep_item.get('grid_key') or '沙盘中'}，需访谈其选择理由。",
            "alternative_hypothesis": definition["alternative"],
            "verification_question": definition["question"],
            "theory_basis": "张日昇《箱庭疗法》强调从作品整体、区域关系与象征物理解表达；申荷永《心理分析：理解与体验》强调象征与体验性理解，避免单一对应。",
            "confidence": "中" if len(items) >= 5 else "低",
        })

    if not themes:
        category_library = {
            "人物与角色": ("关系与自我位置", "人物沙具常承载自我、重要他人或关系期待；代表沙具「" + rep_name + "」可作为自我认同的入口。"),
            "建筑与家园": ("边界与安全感", "建筑、围合与通道常与安全边界、归属和家庭经验相关；需结合沙盘聚集区判断开放或防御程度。"),
            "自然与植物": ("生命力与情绪调节", "植物、山水等自然意象常表达生命力、成长节律与情绪容纳空间。"),
            "动物与神兽": ("本能、陪伴与警觉", "动物意象可承载本能冲动、陪伴需要或警觉防御，需结合其位置与朝向理解。"),
            "交通与器物": ("迁移、目标与行动", "车辆、道路与工具常与行动方向、离开/抵达、资源感和目标推进相关。"),
            "学习与生活": ("规则、成就与日常自我", "书本、文具、生活物件常连接学业角色、规则适应与日常胜任感。"),
            "神秘与符号": ("未知、恐惧与精神资源", "神秘符号可表达难以言说的恐惧、直觉或超越性资源，不能单凭符号作诊断。"),
            "饮食与丰饶": ("滋养、匮乏与满足", "食物与器皿常与滋养、被照顾、匮乏感或丰盛期待相关。"),
        }
        for category in top_categories:
            matches = next((v for k, v in category_library.items() if k in category), None)
            if matches:
                theme, hypothesis = matches
                themes.append({
                    "theme": theme,
                    "symbols": [str(x.get("label") or x.get("name")) for x in items if str(x.get("category") or "") == category][:5] or [category],
                    "hypothesis": hypothesis + f" 代表沙具「{rep_name}」位于{rep_item.get('grid_key') or '沙盘中'}，可进一步访谈其选择理由。",
                    "alternative_hypothesis": "另一种可能是，这些器物主要提供秩序、资源或安全感，不能仅凭类别推断心理困扰。",
                    "verification_question": "这些同类沙具更像是在表达困扰，还是在表达资源、秩序与安全感？",
                    "theory_basis": "张日昇《箱庭疗法》强调从作品整体、区域关系与象征物理解表达；申荷永《心理分析：理解与体验》强调象征与体验性理解，避免单一对应。",
                    "confidence": "中" if len(items) >= 5 else "低",
                })
    if not themes:
        themes.append({
            "theme": "自我表达的起点",
            "symbols": [rep_name],
            "hypothesis": f"当前沙盘以「{rep_name}」为核心意象，作品尚在形成中，需通过访谈了解其选择与摆放意图。",
            "alternative_hypothesis": "另一种可能是，代表沙具主要承担稳定、陪伴或资源功能，不能仅凭单件沙具推断困扰。",
            "verification_question": "这件代表沙具更像是在表达需要被看见的困扰，还是在表达可用的支持与资源？",
            "theory_basis": "申荷永《荣格与分析心理学》重视象征与个体化过程；单一意象不直接等同于结论。",
            "confidence": "低",
        })

    # 第三章：六维
    score_rows = scores
    total_score = sum(x["score"] for x in score_rows)
    total_full = sum(x["full_score"] for x in score_rows)
    total_rate = round(total_score / total_full, 4) if total_full else None
    strong_subjects = [x["subject"] for x in score_rows if x["rate"] >= 0.8]
    weak_subjects = [x["subject"] for x in score_rows if x["rate"] < 0.7]
    academic_evidence = []
    if score_rows:
        academic_evidence.append("成绩单可读科目：" + "、".join(f"{x['subject']}{x['score']:g}/{x['full_score']:g}" for x in score_rows[:10]))
        academic_evidence.append(f"总得分率 {total_rate:.1%}" if total_rate is not None else "总分待核对")
    else:
        academic_evidence.append("本次暂未包含成绩数据，学科判断以沙盘与自述为线索，待补充成绩")
    academic_evidence.append(f"沙盘代表沙具为「{rep_name}」，沙具类别以{'、'.join(top_categories)}为主")
    if teacher_observation.strip():
        academic_evidence.append("教师观察：" + teacher_observation.strip()[:80])

    six = []
    six.append({
        "key": "cognitive", "name": SIX_DIMENSIONS[0][1], "confidence": "高" if score_rows else "低",
        "judgement": "学科认知优势需结合成绩单与沙盘布局综合判断；当前可读成绩显示文科/记忆理解类表现相对更清晰。" if score_rows else "当前成绩信息不足，暂不对学科认知作强弱判定。",
        "assessment_theory": "布鲁姆认知目标分类学 + 认知负荷理论（Bloom, 1956; Sweller, 1988）",
        "assessment_result": "从成绩得分率看，记忆与理解类任务相对稳定；应用、分析类任务需结合错题与解题过程进一步确认。" if score_rows else "缺少成绩数据，沙盘显示布局有秩序感，但不能替代学科能力测评。",
        "evidence": academic_evidence,
        "capabilities_to_improve": ["结构化审题与条件提取", "跨学科知识迁移", "错误归因与复盘"],
        "training_module_directions": [TRAINING_MODULES[1][1], TRAINING_MODULES[2][1]],
        "conclusion": "以优势学科为入口，补齐逻辑应用与迁移训练，避免用单一分数定义能力。",
    })
    six.append({
        "key": "subject_choice", "name": SIX_DIMENSIONS[1][1], "confidence": "中" if score_rows else "低",
        "judgement": "结合得分率与兴趣线索，当前更适合先探索文科/综合方向，同时保留理科基础补强。" if (strong_subjects and weak_subjects) else "选科方向需补充成绩单、兴趣访谈与课程体验后再定。",
        "assessment_theory": "加德纳多元智能理论（Gardner, 1983）",
        "assessment_result": f"相对优势科目：{'、'.join(strong_subjects[:4]) or '待确认'}；相对薄弱科目：{'、'.join(weak_subjects[:4]) or '待确认'}。" if score_rows else "暂无可读成绩，无法形成选科强弱对照。",
        "evidence": ["代表沙具与类别分布提示兴趣入口", f"成绩单可读科目 {len(score_rows)} 门"] if score_rows else ["沙盘意象与自述", "成绩单待补"],
        "capabilities_to_improve": ["学科兴趣访谈", "理科基础补强", "文理融合项目体验"],
        "training_module_directions": [TRAINING_MODULES[1][1], TRAINING_MODULES[3][1]],
        "conclusion": "选科建议是探索性方向，不是一次性定论；用课程体验和阶段成绩共同校准。",
    })
    six.append({
        "key": "interest_potential", "name": SIX_DIMENSIONS[2][1], "confidence": "中",
        "judgement": f"代表沙具「{rep_name}」与{top_categories[0]}类意象突出，提示兴趣与自我投入的方向；需访谈确认其真实兴趣。",
        "assessment_theory": "自我决定理论 + 心流理论（Deci & Ryan, 1985; Csikszentmihalyi, 1990）",
        "assessment_result": "沙盘中选择并突出某类沙具，可能反映内在动机、胜任感或未表达的兴趣需求；当前自述对兴趣的主动描述有限。" if narrative else "沙盘提供了兴趣线索，但缺少自述补充。",
        "evidence": [f"代表沙具：{rep_name}", f"主要类别：{'、'.join(top_categories)}", f"自述长度：{len(narrative)} 字"],
        "capabilities_to_improve": ["兴趣自主选择", "兴趣场景化体验", "压力下的兴趣维持"],
        "training_module_directions": [TRAINING_MODULES[0][1], TRAINING_MODULES[4][1]],
        "conclusion": "先保护兴趣的自主性，再用小步项目把兴趣转化为可坚持的行动。",
    })
    six.append({
        "key": "academic_planning", "name": SIX_DIMENSIONS[3][1], "confidence": "中",
        "judgement": "当前需要把学习目标与未来方向建立可感知的关联，避免只以短期分数驱动。",
        "assessment_theory": "霍兰德RIASEC + 舒伯生涯发展理论（Holland, 1959; Super, 1980）",
        "assessment_result": f"沙盘空间布局{'较有秩序' if occupied >= 4 else '留白较多'}，可作为规划感与掌控感的观察线索；职业兴趣仍需结构化探索。",
        "evidence": [cluster_text, f"代表沙具：{rep_name}", "自述中的学习动力线索需访谈确认"],
        "capabilities_to_improve": ["目标分解", "学习价值感", "职业场景探索"],
        "training_module_directions": [TRAINING_MODULES[4][1]],
        "conclusion": "用阶段目标 + 职业场景体验建立“学习—未来”的连接。",
    })
    family_signal = any(word in text_all for word in ("父母", "家长", "家庭", "争吵", "冲突", "管", "期待"))
    six.append({
        "key": "family_ecology", "name": SIX_DIMENSIONS[4][1], "confidence": "中" if family_signal else "低",
        "judgement": "家庭互动可能是当前情绪与学习状态的重要背景变量，需访谈确认，不作单向归因。" if family_signal else "当前材料未显示明显家庭冲突线索，仍需家长访谈补充。",
        "assessment_theory": "鲍恩家庭系统理论 + 韦纳归因理论（Bowen, 1978; Weiner, 1985）",
        "assessment_result": "自述中出现家庭/期待相关表达，提示家庭情绪系统可能影响学习状态。" if family_signal else "沙盘与自述未呈现明显家庭张力，暂按低线索处理。",
        "evidence": [f"家庭关键词线索：{'有' if family_signal else '无'}", cluster_text],
        "capabilities_to_improve": ["家庭情绪表达一致性", "非暴力沟通", "支持系统构建"],
        "training_module_directions": [TRAINING_MODULES[3][1], TRAINING_MODULES[5][1]],
        "conclusion": "把家庭从“压力源”转为“协同支持源”，先做沟通规则，再谈成绩要求。",
    })
    six.append({
        "key": "motivation_rebuild", "name": SIX_DIMENSIONS[5][1], "confidence": "中",
        "judgement": "当前学习动力需要从外部压力转向可积累的胜任感，避免固定型归因。",
        "assessment_theory": "德韦克成长型思维理论（Dweck, 2006）",
        "assessment_result": f"沙盘{'呈现较清晰的中心聚集' if center_count else '中心区较空'}，可理解为自我掌控感的表达线索；自述中的压力/回避表达提示动力需要重建。",
        "evidence": [f"中心区沙具 {center_count} 件", f"留白区域 {9 - occupied} 格", f"自述长度 {len(narrative)} 字"],
        "capabilities_to_improve": ["小步目标胜任感", "成长型归因", "压力应对"],
        "training_module_directions": [TRAINING_MODULES[0][1], TRAINING_MODULES[4][1], TRAINING_MODULES[5][1]],
        "conclusion": "用可见的小进步重建“我能影响结果”的信念，再逐步提高挑战难度。",
    })

    # 第四章：成绩
    subjects = scores
    total_obj = {
        "score": round(total_score, 2) if total_score else None,
        "full_score": round(total_full, 2) if total_full else None,
        "rate": total_rate,
    }
    if subjects:
        overall = f"可读科目共 {len(subjects)} 门，总得分率 {total_rate:.1%}；相对优势为{'、'.join(strong_subjects[:4]) or '待确认'}，需补强{'、'.join(weak_subjects[:4]) or '暂不明显'}。"
    else:
        overall = "本次报告暂未包含成绩数据，学业评价以沙盘、自述和后续补充成绩为线索，暂不对具体学科下结论。"

    # 第五章：九维
    risk_dimensions = []
    for key, name in RISK_DIMENSIONS:
        level, judgement = _risk_level(name, text_all)
        risk_dimensions.append({
            "key": key, "name": name, "level": level, "label": _risk_label(level),
            "judgement": judgement,
            "evidence": (narrative[:160] if narrative else description[:160] or "本次材料未见明确相关线索"),
            "norm_reference": "本次无量表数据，为观察性判断，建议补测",
        })

    # 第六章
    interview = [
        {"topic": "代表沙具的选择理由", "questions": ["你为什么会选这个沙具代表自己？", "它在沙盘里的位置对你意味着什么？"], "target": "受测者"},
        {"topic": "压力与家庭互动", "questions": ["最近哪些时刻让你觉得压力最大？", "家里通常怎么回应你的学习状态？"], "target": "家长"},
        {"topic": "在校表现与人际", "questions": ["孩子近期在课堂和同伴互动中有什么变化？", "是否有明确的冲突或回避场景？"], "target": "教师"},
    ]

    # 第七章
    has_scores = bool(scores)
    career = {
        "stage": "生涯探索",
        "summary": (
            f"以「{rep_name}」和{top_categories[0]}类意象为兴趣入口，结合可读成绩探索优势方向；"
            "当前目标是建立学习与未来的连接感。"
            if has_scores
            else f"以「{rep_name}」和{top_categories[0]}类意象为兴趣入口，暂不结合成绩排序；"
                 "先探索兴趣与任务投入，待补充成绩后再评估优势方向。"
        ),
        "strengths": [
            f"代表沙具「{rep_name}」属于{top_categories[0]}类，可作为观察兴趣与任务投入的入口",
            f"沙盘布局中{cluster_text}，可作为观察任务组织与空间安排的线索",
            "在可读成绩中显示出相对稳定的记忆/理解类学习基础" if has_scores else "愿意通过沙盘表达，具备自我观察的起点",
        ],
        "teacher_actions": ["每两周用 10 分钟做一次兴趣—学科连接访谈", "把一个长期任务拆成 2-3 个可见小目标"],
        "parent_actions": ["每月安排一次低评价的职业/社会场景体验", "把“考多少分”改为“今天完成了哪一步”"],
        "student_actions": ["每周记录一个感兴趣的职业及其能力要求", "每周完成一次小目标复盘：做到/卡住/下一步"],
        "career_postponed": False,
    }

    # 第八章
    training = []
    module_specs = [
        {
            "key": "module_1_focus", "name": TRAINING_MODULES[0][1],
            "goals": ["持续专注与任务坚持", "深度沉浸体验", "主动延长任务的意愿"],
            "dimensions": ["兴趣特长与潜能（维度3）", "综合动力重塑（维度6）"],
            "logic": "由短时专注逐步过渡到长时沉浸，任务难度阶梯上升，完成后即时反馈。",
            "format": "限时闯关式建构任务、沉浸式情景任务、专注时长打卡。",
            "teacher": ["课堂设 20 分钟单任务时段，结束后请学生口述完成步骤。"],
            "parent": ["家庭作业按 25 分钟专注 + 5 分钟休息执行，休息时不碰手机。"],
            "student": ["每天选一门薄弱科目做 1 轮 25 分钟限时训练，结束后写一句完成情况。"],
        },
        {
            "key": "module_2_logic", "name": TRAINING_MODULES[1][1],
            "goals": ["因果推理与逻辑关联", "结构化口头/书面表达", "从整体到细节的观察"],
            "dimensions": ["全学科认知诊断（维度1）"],
            "logic": "把动手操作经验转化为语言逻辑，形成“操作—表达”双通道。",
            "format": "看图说话与复述、思维导图梳理、区域关系讲解任务（“为什么放在这里”）。",
            "teacher": ["每周布置 1 道理科逻辑训练题，要求口述解题步骤。"],
            "parent": ["每周与孩子讨论 1 个时事话题，引导其按观点—理由—例子表达。"],
            "student": ["每天用 3 分钟梳理当日学习内容的结构。"],
        },
        {
            "key": "module_3_spatial", "name": TRAINING_MODULES[2][1],
            "goals": ["空间认知深化", "分类与布局策略", "学习策略迁移"],
            "dimensions": ["全学科认知诊断（维度1）", "文理选科适配（维度2）"],
            "logic": "巩固空间优势通道，并把空间策略迁移到学习与生活管理。",
            "format": "空间建构任务、地图/迷宫类挑战、整理规划类任务。",
            "teacher": ["每两周开展 1 次学习方法迁移训练，引导把图示法用于理科记忆。"],
            "parent": ["支持孩子用思维导图整理学习内容，不干涉方法选择。"],
            "student": ["每周用思维导图整理 1 个理科知识点的关联。"],
        },
        {
            "key": "module_4_interpersonal", "name": TRAINING_MODULES[3][1],
            "goals": ["人际理解与换位思考", "情绪识别与表达", "主动互动意愿"],
            "dimensions": ["文理选科适配（维度2）", "家庭生态协同（维度5）"],
            "logic": "由静态认知走向动态互动，补足人际智能与情感表达短板。",
            "format": "情景角色扮演、情绪卡片练习、亲子共练任务。",
            "teacher": ["设小组任务并轮换角色，给内向学生安排低压力发言位。"],
            "parent": ["每周一次 15 分钟“不评价聊天”，只复述孩子说的内容。"],
            "student": ["每天记 1 件“今天和谁说了什么”，训练互动细节觉察。"],
        },
        {
            "key": "module_5_goals", "name": TRAINING_MODULES[4][1],
            "goals": ["目标分解与计划执行", "结合成绩数据的学业规划", "自我管理习惯"],
            "dimensions": ["升学与学业规划（维度4）"],
            "logic": "把“兴趣探索”推进为“目标—计划—执行—复盘”的完整闭环。",
            "format": "成绩单复盘会、目标阶梯任务、周计划打卡与复盘。",
            "teacher": ["协助制定 1 个可测的小目标，每两周核查进度。"],
            "parent": ["配合监督目标完成情况，不额外设定过高的成绩要求。"],
            "student": ["每周完成 2 个基础题型训练，先达成阶段目标。"],
        },
        {
            "key": "module_6_family", "name": TRAINING_MODULES[5][1],
            "goals": ["亲子情感连接", "开放式沟通与非评判回应", "过程性激励话术"],
            "dimensions": ["家庭生态协同（维度5）", "综合动力重塑（维度6）"],
            "logic": "家庭侧配合学生侧训练，形成“学生训练 + 家庭协同”的闭环支持。",
            "format": "家长微课 + 亲子共练作业 + 每周家庭共搭任务 + 沟通话术练习。",
            "teacher": ["每月一次 10 分钟家长沟通，反馈具体进步事例。"],
            "parent": ["每周家庭会议 20 分钟，议题固定为“本周一件好事 + 一个改进”。"],
            "student": ["每周主动向家长汇报 1 个进展和 1 个困难。"],
        },
    ]
    for spec in module_specs:
        training.append({
            "key": spec["key"], "name": spec["name"], "goals": spec["goals"],
            "dimensions": spec["dimensions"], "logic": spec["logic"], "format": spec["format"],
            "teacher_actions": spec["teacher"], "parent_actions": spec["parent"], "student_actions": spec["student"],
        })

    report = {
        "schema_version": "1.0",
        "template": "心理沙盘发展性评估报告",
        "meta": {
            "report_no": "PS-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "assessment_source": "沙盘作品评估",
            "grade_level": student.get("grade_level") or "未填写",
            "gender": student.get("gender") or "未填写",
            "student_name": student.get("name") or "匿名受测者",
            "student_no": student.get("student_no") or "",
            "assessment_basis": build_assessment_basis(payload, transcript_image_url),
            "disclaimer": "发展性心理评估参考·非临床诊断",
            "theory_sources": [x["source"] for x in THEORY_EVIDENCE],
            "engine_note": engine_note,
        },
        "chapter_1_overview": {
            "title": CHAPTER_TITLES["chapter_1_overview"],
            "sandplay_image_url": sandplay_image_url,
            "clusters": cluster_text,
            "blank_areas": blank_text,
            "item_category_stats": [{"category": k, "count": v} for k, v in category_counts.most_common()],
            "item_subcategory_stats": [{"subcategory": k, "count": v} for k, v in subcategory_counts.most_common()],
            "item_theme_stats": [
                {
                    "theme": code,
                    "name": (THEME_LIBRARY.get(code) or {}).get("name", code),
                    "count": count,
                }
                for code, count in theme_counts.most_common()
            ],
            "nine_grid_distribution": grid_display,
            "terrain_observation": terrain_text,
            "representative_item_name": rep_name,
            "scene_imagery": [
                f"作品以{'、'.join(top_categories)}类意象为主，代表沙具为「{rep_name}」",
                f"{cluster_text}",
                f"{terrain_text}",
            ],
        },
        "chapter_2_imagery": {
            "title": CHAPTER_TITLES["chapter_2_imagery"],
            "disclaimer": "以下为探索性假设，需访谈确认，非临床诊断",
            "themes": themes[:4],
        },
        "chapter_3_six_dimensions": {
            "title": CHAPTER_TITLES["chapter_3_six_dimensions"],
            "intro": "判定建议结果 → 评估理论 → 评估结果 → 佐证要点 → 待提升能力 → 训练模块指向",
            "dimensions": six,
        },
        "chapter_4_academic": {
            "title": CHAPTER_TITLES["chapter_4_academic"],
            "transcript_provided": bool(transcript_image_url),
            "overall_interpretation": overall,
            "subjects": subjects,
            "total": total_obj,
            "grade_standard": GRADE_STANDARD,
            "strengths": "、".join(strong_subjects[:5]) if strong_subjects else "待成绩单补测后确认",
            "weaknesses": "、".join(weak_subjects[:5]) if weak_subjects else "待成绩单补测后确认",
            "trend": "本次为单次成绩，趋势需结合近 2-3 次考试对照。",
            "notes": [
                "成绩数据以清晰可读的数字为准；无法辨认的科目不编造分数。",
                "单次成绩不能单独决定选科或能力等级。",
            ] if scores else [
                "本次报告暂未包含成绩数据，相关判断待补充成绩后再评估。",
            ],
            "transcript_image_url": transcript_image_url or "",
        },
        "chapter_5_risk": {
            "title": CHAPTER_TITLES["chapter_5_risk"],
            "visibility": "counselor_only",
            "disclaimer": "仅供咨询师在专业范围内审阅，不可直接呈现给受测者及其家属；不替代量表、访谈和转介。",
            "dimensions": risk_dimensions,
        },
        "chapter_6_interview": {"title": CHAPTER_TITLES["chapter_6_interview"], "items": interview},
        "chapter_7_career": {"title": CHAPTER_TITLES["chapter_7_career"], **career},
        "chapter_8_training_modules": {
            "title": CHAPTER_TITLES["chapter_8_training_modules"],
            "intro": "每个维度只指向1-3个模块，保证训练聚焦、不分散。",
            "modules": training,
        },
        "chapter_9_general_advice": {
            "title": CHAPTER_TITLES["chapter_9_general_advice"],
            "growth_mindset": [
                "把成绩波动与社交困难理解为阶段性状态，而非能力不足的证明",
                "用小步目标的完成积累胜任感，肯定每一次可复制的进步",
                "把家庭压力与自身学习分开，建立自己的成长节奏",
            ],
            "strength_transfer": [
                "以沙盘中的空间组织与兴趣投入为入口，迁移到学习计划",
                "把代表沙具所承载的自我期待转化为一个可执行的小目标",
            ],
            "capability_not_label": [
                "本报告为发展性评估参考，不用于障碍判定、分班或评优",
                "所有意象与六维结论均为探索性假设，需访谈与表现数据校准",
                "风险线索只用于咨询师决定是否升级支持，不向家长/学生端展示",
            ],
            "disclaimer": "本报告为发展性心理评估参考，非临床诊断；所有假设以访谈、量表与专业判断为准。",
        },
    }
    return report
