from __future__ import annotations

import unittest

from app import report_engine
from app.holistic import normalize_screen
from app.utils import public_copy


RISK_DIMENSIONS = list(report_engine.RISK_DIMENSIONS)


def _base_report() -> dict:
    return {
        "meta": {"generated_at": "2026-11-22T10:00:00+00:00", "report_no": "PS-TEST"},
        "chapter_1_overview": {
            "representative_item_name": "桥",
            "holistic_visual_check": {"risk_level": "none", "visual_risk_objects": []},
        },
        "chapter_2_imagery": {"themes": [{"theme": "边界与连接"}]},
        "chapter_5_risk": {
            "dimensions": [
                {"key": key, "name": name, "level": "L1", "label": "L1 平稳"}
                for key, name in RISK_DIMENSIONS
            ]
        },
        "chapter_6_interview": {
            "items": [{"topic": "边界", "questions": ["你放这座桥时，最希望谁走过来？"], "target": "受测者"}]
        },
        "chapter_7_career": {"strengths": ["能主动建立连接"], "stage": "生涯探索"},
        "chapter_9_general_advice": {
            "growth_mindset": ["先把这次沙盘当作一次表达，而不是一次考试。"],
            "strength_transfer": [],
            "capability_not_label": [],
            "disclaimer": "发展性参考",
        },
    }


def _payload(**extra) -> dict:
    payload = {
        "student": {"name": "测试学生", "student_no": "S-001"},
        "representative_item_id": "item-bridge",
        "representative_item_name": "桥",
        "self_image": "一盏灯",
        "sandplay_description": "我在中间放了一座桥，两侧各放了一个人。",
        "teacher_observation": "近期课堂表现平稳。",
        "items": [],
    }
    payload.update(extra)
    return payload


class RiskPriorityTests(unittest.TestCase):
    def test_single_non_death_high_risk_item_is_l3(self):
        payload = _payload(items=[{"id": "i1", "label": "坦克", "risk_tier": "high_risk"}])
        priority = report_engine._detect_priority(_base_report(), payload, None)
        self.assertEqual(priority["level"], "L3_ORANGE")
        self.assertIn("单件高危沙具", " ".join(priority["triggers"]))

    def test_death_item_is_l4(self):
        payload = _payload(items=[{"id": "i1", "label": "骷髅", "risk_tier": "high_risk"}])
        priority = report_engine._detect_priority(_base_report(), payload, None)
        self.assertEqual(priority["level"], "L4_RED")

    def test_two_high_risk_items_are_l4(self):
        payload = _payload(items=[
            {"id": "i1", "label": "匕首", "risk_tier": "high_risk"},
            {"id": "i2", "label": "铁牢笼", "risk_tier": "high_risk"},
        ])
        priority = report_engine._detect_priority(_base_report(), payload, None)
        self.assertEqual(priority["level"], "L4_RED")
        self.assertIn("多件高危沙具", " ".join(priority["triggers"]))

    def test_single_visual_firearm_is_l3(self):
        screen = normalize_screen({
            "visual_risk_level": "high",
            "visual_risk_objects": [{
                "type": "firearm",
                "label": "步枪",
                "location": "左侧楼房旁",
                "orientation": "枪口朝下",
                "person_relation": "附近无人",
                "scene_context": "城市街景",
                "severity": "high",
                "evidence": "枪身清晰可见",
            }],
        })
        payload = _payload(_holistic_screen=screen)
        priority = report_engine._detect_priority(_base_report(), payload, None)
        self.assertEqual(priority["level"], "L3_ORANGE")
        self.assertIn("单件视觉高危物体", " ".join(priority["triggers"]))

    def test_visual_corpse_is_l4(self):
        screen = normalize_screen({
            "visual_risk_level": "high",
            "visual_risk_objects": [{
                "type": "corpse",
                "label": "倒地人形",
                "location": "右下角",
                "orientation": "平躺",
                "person_relation": "旁边无人",
                "scene_context": "废墟",
                "severity": "high",
                "evidence": "人形长时间倒地",
            }],
        })
        payload = _payload(_holistic_screen=screen)
        priority = report_engine._detect_priority(_base_report(), payload, None)
        self.assertEqual(priority["level"], "L4_RED")
        self.assertIn("视觉死亡符号", " ".join(priority["triggers"]))

    def test_display_weapon_watch_does_not_raise_priority(self):
        screen = normalize_screen({
            "visual_risk_level": "watch",
            "visual_risk_objects": [{
                "type": "firearm",
                "label": "玩具步枪",
                "location": "军事陈列区",
                "orientation": "朝上陈列",
                "person_relation": "不指向人物",
                "scene_context": "博物馆陈列",
                "severity": "watch",
                "evidence": "放在展架上",
            }],
        })
        payload = _payload(_holistic_screen=screen)
        priority = report_engine._detect_priority(_base_report(), payload, None)
        self.assertIsNone(priority)


class SummaryAndComparisonTests(unittest.TestCase):
    def test_self_image_is_written_to_chapter2_without_changing_risk(self):
        report = _base_report()
        payload = _payload()
        report_engine._ensure_self_image_section(report, payload)
        self.assertEqual(report["chapter_2_imagery"]["self_image"]["name"], "一盏灯")
        self.assertIn("不直接决定风险等级", report["chapter_2_imagery"]["self_image"]["risk_boundary"])
        self.assertEqual(report_engine._risk_dimension_levels(report)["self_harm"], "L1")

    def test_longitudinal_comparison_and_summary(self):
        report = _base_report()
        payload = _payload(_previous_assessment={
            "assessment_id": "old-1",
            "report_no": "PS-OLD",
            "created_at": "2026-09-01T10:00:00+00:00",
            "generated_at": "2026-09-01T10:00:00+00:00",
            "engine": "multimodal",
            "lean_only": False,
            "representative_item_name": "围墙",
            "self_image": "蹲着的人",
            "risk_dimensions": [
                {"key": "depression", "name": "抑郁", "level": "L2", "label": "L2 轻度关注"},
                {"key": "self_harm", "name": "自我伤害倾向", "level": "L2", "label": "L2 轻度关注"},
            ],
        })
        report_engine._ensure_self_image_section(report, payload)
        report_engine._ensure_longitudinal_comparison(report, payload)
        comparison = report["longitudinal_comparison"]
        self.assertTrue(comparison["available"])
        self.assertEqual(comparison["improved"], 2)
        self.assertEqual(comparison["previous_risk_count"], 2)
        self.assertIn("缺少7个维度", comparison["note"])
        self.assertIn("2026-09-01", comparison["previous_date"])

        report_engine._ensure_summary_card(report, payload)
        card = report["summary_card"]
        self.assertTrue(card["headline"])
        self.assertEqual(card["risk_overview"]["count"], 0)
        self.assertEqual(card["risk_overview"]["previous_count"], 2)
        self.assertTrue(card["public"]["headline"])
        self.assertNotIn("risk_overview", card["public"])
        self.assertIn("一盏灯", card["public"]["next_step"])

    def test_public_copy_removes_risk_and_summary_risk(self):
        report = _base_report()
        report["summary_card"] = {
            "headline": "咨询师标题",
            "risk_overview": {"count": 2, "highest_level": "L3"},
            "public": {"headline": "家长标题", "signals": [], "next_step": "下一步"},
        }
        report["chapter_5_risk"]["dimensions"][0]["level"] = "L3"
        report["meta"]["quality_flags"] = ["VISUAL_RISK_OBJECT", "HOLISTIC_SCREEN_MISSING", "KEEP_FLAG"]
        report["meta"]["quality_warnings"] = [
            {"code": "VISUAL_RISK_OBJECT", "message": "视觉高危物体"},
            {"code": "KEEP_WARNING", "message": "保留"},
        ]
        report["meta"]["student_name"] = "李瑶"
        report["meta"]["student_no"] = "PS-QUICK"
        report["meta"]["process_metrics"] = {"long_pause_count": 1}
        report["meta"]["generation_usage"] = {"total_tokens": 100}
        public = public_copy(report)
        self.assertNotIn("chapter_5_risk", public)
        self.assertNotIn("risk_overview", public.get("summary_card", {}))
        self.assertEqual(public["summary_card"]["headline"], "家长标题")
        self.assertNotIn("quality_flags", public["meta"])
        self.assertNotIn("quality_warnings", public["meta"])
        self.assertNotIn("student_name", public["meta"])
        self.assertNotIn("student_no", public["meta"])
        self.assertNotIn("process_metrics", public["meta"])
        self.assertNotIn("generation_usage", public["meta"])


if __name__ == "__main__":
    unittest.main()
