"""数据链路回归：terrain_metrics / process_telemetry / raw_record_echo。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.demo_report import build_demo_report  # noqa: E402
from app.report_engine import normalize_meta, validate_report  # noqa: E402
from app.utils import public_copy  # noqa: E402


def payload(*, terrain_edited=True, telemetry=None):
    return {
        "student": {"name": "链路测试", "grade_level": "初一", "gender": "女", "student_no": "L-001"},
        "items": [
            {"id": "NEUTRAL_016", "label": "展开的双手", "category": "神秘与象征符号",
             "themes": ["transformation"], "risk_tier": "none", "grid_key": "A1"},
            {"id": "BUILDING_001", "label": "小屋 · 安全居所", "category": "建筑与居所",
             "themes": [], "risk_tier": "none", "grid_key": "C3"},
        ],
        "representative_item_id": "NEUTRAL_016",
        "representative_item_name": "展开的双手",
        "sandplay_description": "中心是展开的双手，右下角有一座小屋，前方挖出水域。",
        "self_narrative": "我想表达一种被接住的感觉。",
        "teacher_observation": "该生在制作时多次调整双手的位置，完成后主动说明水面代表情绪。",
        "grid_distribution": {"summary": {"occupied_cells": 3, "center_count": 1}, "clusters": [{"label": "中心区", "count": 1}]},
        "heightmap": {"values": [0, 2.5, -20, 4.0, 0]},
        "terrain_metrics": {
            "terrain_edited": terrain_edited,
            "water_area_pct": 20.0 if terrain_edited else 0,
            "mound_area_pct": 40.0 if terrain_edited else 0,
            "elevation_range": 24.0 if terrain_edited else 0,
            "terrain_summary": (
                "已进行明显地形塑形：挖出水域约占 20.0%（中心区 0.0%、周边 20.0%），局部隆起形成沙岛/沙丘约占 40.0%，高程差约 24.0。"
                if terrain_edited else "沙面基本平整，未进行明显地形塑形。"
            ),
        },
        "process_telemetry": telemetry or {
            "total_duration_sec": 326,
            "item_added_total": 4,
            "item_deleted_total": 1,
            "hesitation_count": 3,
            "terrain_stroke_count": 7,
            "bury_actions": [],
            "destructive_loops": 0,
            "undo_count": 1,
        },
        "interaction_summary": {"tool": "brush", "brush_size": 2, "camera_distance": 5},
    }


def build(p):
    report = build_demo_report(p, sandplay_image_url="http://example.com/sandplay.png", transcript_image_url=None)
    report = validate_report(report)
    return normalize_meta(report, payload=p, image_url="http://example.com/sandplay.png", transcript_url=None, engine="demo")


def main():
    report = build(payload())
    chapter1 = report["chapter_1_overview"]
    assert chapter1["terrain_observation"].startswith("已进行明显地形塑形"), chapter1["terrain_observation"]
    assert "沙盘地形高度图" in report["meta"]["assessment_basis"]
    assert chapter1["representative_item_name"] == "展开的双手"
    assert report["raw_record_echo"]["teacher_observation"].startswith("该生在制作时多次调整")
    assert report["raw_record_echo"]["self_narrative"] == "我想表达一种被接住的感觉。"
    assert "制作总耗时 5 分 26 秒" in report["meta"]["client_inputs"]["process_note"]
    assert "累计放入 4 件" in report["meta"]["client_inputs"]["process_note"]
    assert "推沙/挖水 7 笔" in report["meta"]["client_inputs"]["process_note"]
    assert "本次未采集制作耗时" not in report["meta"]["client_inputs"]["process_note"]
    assert "raw_record_echo" not in public_copy(report)

    flat = build(payload(terrain_edited=False))
    assert "沙盘地形高度图" not in flat["meta"]["assessment_basis"]
    assert flat["chapter_1_overview"]["terrain_observation"] == "沙面基本平整，未进行明显地形塑形。"

    legacy = payload(terrain_edited=False)
    legacy.pop("terrain_metrics")
    legacy_flat = build(legacy)
    assert "沙盘地形高度图" not in legacy_flat["meta"]["assessment_basis"]

    l4 = build(payload(telemetry={
        "total_duration_sec": 120,
        "item_added_total": 2,
        "item_deleted_total": 0,
        "hesitation_count": 1,
        "terrain_stroke_count": 2,
        "bury_actions": [{"label": "男孩", "buried_label": "小屋", "at_sec": 70}],
        "destructive_loops": 1,
        "undo_count": 0,
    }))
    assert l4["priority_banner"]["level"] == "L4_RED"
    assert any("掩埋人物" in trigger for trigger in l4["priority_banner"]["triggers"])
    assert any("短时反复放删" in trigger for trigger in l4["priority_banner"]["triggers"])

    print("DATA_LINK_OK")
    print("basis", report["meta"]["assessment_basis"])
    print("terrain", chapter1["terrain_observation"])
    print("process", report["meta"]["client_inputs"]["process_note"])
    print("raw_teacher", report["raw_record_echo"]["teacher_observation"])
    print("l4", l4["priority_banner"]["triggers"])


if __name__ == "__main__":
    main()
