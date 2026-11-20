"""报告算法层回归校验：六维探索、训练决算、九维量表、L3/L4 路由与第三人称。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.demo_report import build_demo_report  # noqa: E402
from app.report_engine import (  # noqa: E402
    _EXPLORATION_DISCLAIMER,
    _EXPLORATION_BLOCKERS,
    _third_person_text,
    normalize_meta,
    validate_report,
)
from app.theory import RISK_INSTRUMENTS, SIX_DIMENSION_THEORIES  # noqa: E402
from app.utils import public_copy  # noqa: E402


def make_payload(*, narrative: str = "", teacher: str = "", items=None, style: str = "normal"):
    base_items = items or [
        {
            "id": "ANIMAL_001", "label": "爷爷 · 家庭与代际", "category": "人物与角色原型",
            "themes": ["transformation"], "risk_tier": "none", "grid_key": "A1",
        },
        {
            "id": "NATURE_001", "label": "大树 · 生长与庇护", "category": "自然山水与植物",
            "themes": ["transformation"], "risk_tier": "none", "grid_key": "B2",
        },
        {
            "id": "BUILDING_001", "label": "小屋 · 安全居所", "category": "建筑与居所",
            "themes": [], "risk_tier": "none", "grid_key": "C3",
        },
    ]
    return {
        "student": {"name": "回归测试", "grade_level": "初一", "gender": "女", "student_no": "T-001"},
        "items": base_items,
        "representative_item_id": base_items[0]["id"],
        "representative_item_name": base_items[0]["label"],
        "sandplay_description": "沙盘中放置了家庭人物、树木与小屋，中心区较集中。",
        "self_narrative": narrative,
        "teacher_observation": teacher,
        "grid_distribution": {
            "summary": {"occupied_cells": 5, "center_count": 2},
            "clusters": [{"label": "中心区", "count": 2}],
        },
        "heightmap": {"values": [0.0, 0.1, -0.1, 0.05, 0.2]},
        "interaction_summary": {"tool": "brush", "brush_size": 2, "camera_distance": 5},
        "style": style,
    }


def build(payload):
    report = build_demo_report(
        payload,
        sandplay_image_url="http://example.com/sandplay.png",
        transcript_image_url=None,
    )
    validate_report(report)
    report = normalize_meta(
        report,
        payload=payload,
        image_url="http://example.com/sandplay.png",
        transcript_url=None,
        engine="demo",
    )
    return report


def assert_no_second_person(report):
    blob = "\n".join(
        str(value)
        for key, value in report.items()
        if key.startswith("chapter_") and key != "chapter_6_interview"
        for value in (value.values() if isinstance(value, dict) else [value])
    )
    for word in ("你们", "你家孩子", "孩子你"):
        assert word not in blob, f"发现第二人称：{word}"


def main():
    results = {}

    base = build(make_payload())
    assert base["chapter_3_six_dimensions"]["dimensions"], "缺少六维"
    for dim in base["chapter_3_six_dimensions"]["dimensions"]:
        assert dim["assessment_theory"] == SIX_DIMENSION_THEORIES[dim["name"]], dim["name"]
        assert dim["conclusion"].endswith(_EXPLORATION_DISCLAIMER), dim["name"]
        assert not any(blocker in dim["judgement"] + dim["assessment_result"] + dim["conclusion"]
                       for blocker in _EXPLORATION_BLOCKERS), dim["judgement"]
        assert dim["confidence"] in ("中", "低"), dim["confidence"]
    active = [m for m in base["chapter_8_training_modules"]["modules"] if m.get("active")]
    assert 1 <= len(active) <= 2, len(active)
    dims = {d["name"]: d for d in base["chapter_3_six_dimensions"]["dimensions"]}
    active_dimensions = {
        name for module in active for name in (module.get("dimensions") or [])
    }
    for name, dim in dims.items():
        if name in active_dimensions:
            assert "优先启动" in dim["training_module_directions"][0], name
        else:
            assert "次级观察方向" in dim["training_module_directions"][0], name
    deferred = {m["name"] for m in base["chapter_8_training_modules"]["modules"] if not m.get("active")}
    assert deferred == set(base["chapter_8_training_modules"]["deferred_modules"]), "第八章暂不启动不一致"
    assert "职业发展优势" in base["chapter_7_career"]["title"]
    results["normal"] = {
        "priority": base.get("priority_banner", {}).get("level", "normal"),
        "active_count": len(active),
        "deferred_count": len(deferred),
        "six_confidence": [d["confidence"] for d in base["chapter_3_six_dimensions"]["dimensions"]],
    }

    l4 = build(make_payload(
        narrative="我觉得撑不下去了，不想活，想过跳楼。",
        items=[
            {"id": "CRISIS_007", "label": "骷髅", "category": "神秘与象征符号",
             "themes": ["crisis", "shadow"], "risk_tier": "high_risk", "grid_key": "A1"},
            {"id": "ANIMAL_001", "label": "爷爷 · 家庭与代际", "category": "人物与角色原型",
             "themes": ["transformation"], "risk_tier": "none", "grid_key": "B2"},
        ],
    ))
    assert l4["priority_banner"]["level"] == "L4_RED"
    assert l4["priority_banner"]["checklist_24h"]
    assert l4["chapter_8_training_modules"]["modules"] == [], "L4 必须清空模块"
    assert "保护性因素" in l4["chapter_7_career"]["title"]
    assert l4["chapter_7_career"]["career_postponed"] is True
    public = public_copy(l4)
    assert "priority_banner" not in public, "脱敏版泄露 priority_banner"
    assert "chapter_5_risk" not in public, "脱敏版泄露第五章"
    results["l4"] = {
        "level": l4["priority_banner"]["level"],
        "triggers": l4["priority_banner"]["triggers"],
        "modules": len(l4["chapter_8_training_modules"]["modules"]),
        "chapter7": l4["chapter_7_career"]["title"],
    }

    l3 = build(make_payload(
        teacher="近期被同学霸凌，回家后拒绝交流，情绪明显低落。",
        items=[
            {"id": "BUILDING_069", "label": "天台", "category": "建筑与居所",
             "themes": ["crisis"], "risk_tier": "watch", "grid_key": "A1"},
            {"id": "ANIMAL_001", "label": "爷爷 · 家庭与代际", "category": "人物与角色原型",
             "themes": ["transformation"], "risk_tier": "none", "grid_key": "B2"},
        ],
    ))
    assert l3["priority_banner"]["level"] == "L3_ORANGE"
    assert "保护性因素" in l3["chapter_7_career"]["title"]
    results["l3"] = {
        "level": l3["priority_banner"]["level"],
        "triggers": l3["priority_banner"]["triggers"],
        "modules_total": len(l3["chapter_8_training_modules"]["modules"]),
        "chapter7": l3["chapter_7_career"]["title"],
    }

    risk_dims = l3["chapter_5_risk"]["dimensions"]
    instruments = {d["name"]: d["norm_reference"] for d in risk_dims}
    expected = {name: RISK_INSTRUMENTS[key] for key, name in [
        ("depression", "抑郁"), ("anxiety", "焦虑"), ("learning_pressure", "学习压力感"),
        ("learning_burnout", "学习倦怠"), ("obsession", "强迫"), ("paranoia", "偏执"),
        ("hostility", "敌对"), ("interpersonal_sensitivity", "人际关系敏感"), ("self_harm", "自我伤害倾向"),
    ]}
    assert instruments == expected, instruments
    assert_no_second_person(base)
    assert_no_second_person(l3)
    rewritten = _third_person_text("你要理解孩子，你们家孩子需要支持。")
    assert "你" not in rewritten and "孩子" not in rewritten, rewritten
    assert "受测者" in rewritten, rewritten

    print("REPORT_LOGIC_OK")
    for key, value in results.items():
        print(key, value)
    print("instruments", instruments)


if __name__ == "__main__":
    main()
