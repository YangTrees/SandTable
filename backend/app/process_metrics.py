from __future__ import annotations

from typing import Any


PROCESS_ACTION_KEYS = (
    "total_duration_sec", "item_added_total", "item_deleted_total",
    "item_moved_total", "hesitation_count", "terrain_stroke_count",
    "destructive_loops", "undo_count", "action_count", "first_action_at_sec",
    "last_action_at_sec", "long_pause_count", "longest_pause_sec",
    "post_finish_idle_sec", "action_events", "bury_actions",
)


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def _pick(telemetry: dict[str, Any], legacy: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in telemetry and telemetry.get(key) not in (None, ""):
            return telemetry.get(key)
        if key in legacy and legacy.get(key) not in (None, ""):
            return legacy.get(key)
    return 0


def process_telemetry(payload: dict[str, Any]) -> dict[str, Any]:
    """把新版遥测和旧 interaction_summary 归一到同一套过程指标。"""
    telemetry = payload.get("process_telemetry") if isinstance(payload.get("process_telemetry"), dict) else {}
    legacy = payload.get("interaction_summary") if isinstance(payload.get("interaction_summary"), dict) else {}

    action_events = _pick(telemetry, legacy, "action_events", "events")
    if not isinstance(action_events, list):
        action_events = []
    normalized_events: list[dict[str, Any]] = []
    for event in action_events[:80]:
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("type") or "").strip()
        if not event_type:
            continue
        normalized_events.append({
            "type": event_type[:16],
            "at_sec": _safe_int(event.get("at_sec")),
        })

    bury_actions = _pick(telemetry, legacy, "bury_actions")
    if not isinstance(bury_actions, list):
        bury_actions = []

    added = _safe_int(_pick(telemetry, legacy, "item_added_total", "place_count"))
    deleted = _safe_int(_pick(telemetry, legacy, "item_deleted_total", "delete_count", "remove_count", "removed_count"))
    moved = _safe_int(_pick(telemetry, legacy, "item_moved_total", "item_moved_count", "drag_count", "move_count", "hesitation_count"))
    strokes = _safe_int(_pick(telemetry, legacy, "terrain_stroke_count", "brush_strokes", "raise_sand_count"))
    undo = _safe_int(_pick(telemetry, legacy, "undo_count"))
    action_count = _safe_int(_pick(telemetry, legacy, "action_count"))
    if not action_count:
        action_count = len(normalized_events) or (added + deleted + moved + strokes + undo)

    duration = _safe_int(_pick(telemetry, legacy, "total_duration_sec", "duration_seconds", "elapsed_seconds", "total_seconds"))
    first_action = _safe_int(_pick(telemetry, legacy, "first_action_at_sec", "first_action_sec"))
    last_action = _safe_int(_pick(telemetry, legacy, "last_action_at_sec", "last_action_sec"))
    if duration <= 0 and last_action > 0:
        duration = last_action

    post_finish_idle = _safe_int(_pick(telemetry, legacy, "post_finish_idle_sec", "post_completion_pause_sec"))
    if post_finish_idle <= 0 and duration > 0 and last_action > 0:
        post_finish_idle = max(0, duration - last_action)

    long_pause_count = _safe_int(_pick(telemetry, legacy, "long_pause_count"))
    longest_pause = _safe_int(_pick(telemetry, legacy, "longest_pause_sec"))
    if normalized_events and not long_pause_count:
        times = [event["at_sec"] for event in normalized_events]
        intervals = [b - a for a, b in zip(times, times[1:]) if b >= a]
        long_pause_count = sum(1 for interval in intervals if interval >= 8)
        longest_pause = max(intervals) if intervals else 0

    return {
        "total_duration_sec": duration,
        "item_added_total": added,
        "item_deleted_total": deleted,
        "item_moved_total": moved,
        "hesitation_count": moved,
        "terrain_stroke_count": strokes,
        "destructive_loops": _safe_int(_pick(telemetry, legacy, "destructive_loops")),
        "undo_count": undo,
        "action_count": action_count,
        "first_action_at_sec": first_action,
        "last_action_at_sec": last_action,
        "post_finish_idle_sec": post_finish_idle,
        "long_pause_count": long_pause_count,
        "longest_pause_sec": longest_pause,
        "action_events": normalized_events,
        "bury_actions": [x for x in bury_actions if isinstance(x, dict)][:20],
    }


def has_process_data(payload: dict[str, Any]) -> bool:
    telemetry = process_telemetry(payload)
    if any(telemetry[key] for key in (
        "total_duration_sec", "item_added_total", "item_deleted_total",
        "item_moved_total", "hesitation_count", "terrain_stroke_count",
        "destructive_loops", "undo_count", "action_count",
        "first_action_at_sec", "last_action_at_sec",
    )) or telemetry["bury_actions"]:
        return True
    summary = payload.get("interaction_summary") or {}
    if not isinstance(summary, dict):
        return False
    process_keys = {
        "duration_seconds", "elapsed_seconds", "total_seconds", "total_duration_sec",
        "drag_count", "move_count", "delete_count", "item_added_total", "item_deleted_total",
        "hesitation_count", "undo_count", "undo_steps", "brush_strokes",
        "terrain_stroke_count", "bury_actions", "destructive_loops", "last_item_dwell_seconds",
        "action_count", "action_events", "first_action_at_sec", "last_action_at_sec",
    }
    return any(key in summary for key in process_keys)


def build_process_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    telemetry = process_telemetry(payload)
    available = has_process_data(payload)
    duration = telemetry["total_duration_sec"]
    added = telemetry["item_added_total"]
    moved = telemetry["item_moved_total"]
    deleted = telemetry["item_deleted_total"]
    undo = telemetry["undo_count"]
    strokes = telemetry["terrain_stroke_count"]
    action_count = telemetry["action_count"]
    revision_actions = deleted + moved + undo

    return {
        "available": available,
        "total_duration_sec": duration,
        "item_added_total": added,
        "item_deleted_total": deleted,
        "item_moved_total": moved,
        "undo_count": undo,
        "terrain_stroke_count": strokes,
        "action_count": action_count,
        "first_action_at_sec": telemetry["first_action_at_sec"],
        "last_action_at_sec": telemetry["last_action_at_sec"],
        "post_finish_idle_sec": telemetry["post_finish_idle_sec"],
        "long_pause_count": telemetry["long_pause_count"],
        "longest_pause_sec": telemetry["longest_pause_sec"],
        "seconds_per_item": round(duration / added, 1) if duration and added else None,
        "action_density_per_min": round(action_count / duration * 60, 1) if duration and action_count else None,
        "revision_actions": revision_actions,
        "revision_ratio": round(revision_actions / added, 2) if added else None,
        "terrain_action_share_pct": round(strokes / action_count * 100, 1) if action_count and strokes else 0.0,
        "repetition_risk": bool(telemetry["destructive_loops"] or telemetry["bury_actions"]),
        "destructive_loops": telemetry["destructive_loops"],
        "bury_count": len(telemetry["bury_actions"]),
    }


def format_duration(seconds: int) -> str:
    if seconds <= 0:
        return "未记录"
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours} 小时 {minutes} 分 {sec} 秒"
    if minutes:
        return f"{minutes} 分 {sec} 秒"
    return f"{sec} 秒"


def process_note(payload: dict[str, Any]) -> str:
    telemetry = process_telemetry(payload)
    if not has_process_data(payload):
        return "本次未采集制作耗时、推沙/挖水、修改犹豫次数；仅记录当前交互摘要。"
    parts = [
        f"制作总耗时 {format_duration(telemetry['total_duration_sec'])}",
        f"累计放入 {telemetry['item_added_total']} 件",
        f"删除/撤回 {telemetry['item_deleted_total']} 件",
        f"拖拽调整 {telemetry['item_moved_total']} 次",
        f"推沙/挖水 {telemetry['terrain_stroke_count']} 笔",
    ]
    if telemetry["undo_count"]:
        parts.append(f"撤销 {telemetry['undo_count']} 次")
    if telemetry["action_count"]:
        parts.append(f"过程动作 {telemetry['action_count']} 次")
    if telemetry["long_pause_count"]:
        parts.append(f"长停顿 {telemetry['long_pause_count']} 次（最长 {telemetry['longest_pause_sec']} 秒）")
    if telemetry["post_finish_idle_sec"]:
        parts.append(f"完成后停留 {telemetry['post_finish_idle_sec']} 秒")
    if telemetry["bury_actions"]:
        parts.append(f"掩埋人物 {len(telemetry['bury_actions'])} 次")
    if telemetry["destructive_loops"]:
        parts.append(f"短时反复放删 {telemetry['destructive_loops']} 次")
    return "；".join(parts) + "。"


def _scene_excerpt(scene_text: str) -> str:
    text = " ".join(str(scene_text or "").split())
    if not text:
        return ""
    return text[:90].rstrip("，。；") + ("……" if len(text) > 90 else "")


def build_process_analysis(payload: dict[str, Any], scene_text: str = "") -> dict[str, Any]:
    metrics = build_process_metrics(payload)
    if not metrics["available"]:
        return {
            "available": False,
            "title": "制作过程动力学观察",
            "note": "本次未采集制作耗时、推沙/挖水、拖拽修改、撤销或掩埋等过程数据，因此不做事后推断；仅以作品内容与访谈材料为准。",
            "confidence": "低",
        }

    duration = metrics["total_duration_sec"]
    added = metrics["item_added_total"]
    moved = metrics["item_moved_total"]
    deleted = metrics["item_deleted_total"]
    undo = metrics["undo_count"]
    strokes = metrics["terrain_stroke_count"]
    revision = metrics["revision_actions"]
    per_item = metrics["seconds_per_item"]
    density = metrics["action_density_per_min"]
    terrain_share = metrics["terrain_action_share_pct"]
    first_delay = metrics["first_action_at_sec"]
    post_idle = metrics["post_finish_idle_sec"]
    long_pause = metrics["long_pause_count"]
    longest_pause = metrics["longest_pause_sec"]

    pace_parts = [f"从首次操作到结束约 {format_duration(duration)}，放入 {added} 件沙具"]
    if per_item is not None:
        pace_parts.append(f"平均每件约 {per_item} 秒")
    if density is not None:
        pace_parts.append(f"动作密度约 {density} 次/分钟")
    if first_delay > 10:
        pace_parts.append(f"首次落手前停留约 {first_delay} 秒")
    if long_pause:
        pace_parts.append(f"过程中出现 {long_pause} 次 8 秒以上停顿，最长约 {longest_pause} 秒")
    if post_idle > 10:
        pace_parts.append(f"完成后停留约 {post_idle} 秒")
    if per_item is None:
        pace_hint = "过程时长与件数不足以判断节奏，仅记录可见动作。"
    elif per_item <= 8 and duration <= 90:
        pace_hint = "整体节奏偏紧凑，进入任务和定型较快；这既可能反映决断与整体规划，也可能提示探索深度有限，需访谈区分。"
    elif per_item <= 25:
        pace_hint = "整体节奏中等，摆放与地形操作交替推进，呈现出一定的计划性和持续投入。"
    else:
        pace_hint = "整体节奏较从容或停顿较多，可能反映审慎、沉浸，也可能反映选择困难；需结合长停顿发生的时点判断。"
    pace = "，".join(pace_parts) + "。" + pace_hint

    if revision == 0:
        revision_hint = "整个过程没有删除、拖拽或撤销，属于一次性落位为主；可能反映决断与整体规划较强，也可能提示探索深度有限，不能直接等同于稳定人格。"
    elif metrics["revision_ratio"] is not None and metrics["revision_ratio"] <= 0.5:
        revision_hint = "出现少量试探性调整，说明受测者在落位后仍在核对空间关系，修改幅度可控。"
    else:
        revision_hint = "修改类动作相对较多，提示反复权衡、试探或对结果不满意，需结合修改发生在哪些沙具上理解其冲突焦点。"
    revision_text = (
        f"删除/撤回 {deleted} 次、拖拽调整 {moved} 次、撤销 {undo} 次，"
        f"修改类动作合计 {revision} 次；以放入 {added} 件为参照，修改比为 "
        f"{metrics['revision_ratio'] if metrics['revision_ratio'] is not None else '未计算'}。{revision_hint}"
    )

    if strokes == 0:
        terrain_text = "本次没有记录推沙/挖水笔触，作品以沙具摆放为主；这不等于受测者没有空间控制感，只说明地形维度未提供可用证据。"
    else:
        terrain_text = (
            f"推沙/挖水共 {strokes} 笔，占全部动作的 {terrain_share}%；"
            "地形操作越多，越能说明受测者不只陈列沙具，而是在主动改变沙面、建构情绪容器或边界。"
            "若地形集中在中心区，通常更贴近自我与核心冲突；若集中在外围，则更偏向环境设置与边界防御，需结合实拍复核。"
        )
    if metrics["bury_count"] or metrics["destructive_loops"]:
        terrain_text += (
            f" 过程中记录掩埋人物 {metrics['bury_count']} 次、短时反复放删 {metrics['destructive_loops']} 次，"
            "属于需要优先核实的冲突/破坏—修复线索，不能仅作风格描述。"
        )

    theory = (
        "箱庭理论把制作过程视为与作品内容并列的时间维度：首次落手前的停留、摆放顺序、"
        "修改与撤销，反映受测者接近任务、建立控制感和处理冲突的方式；推沙/挖水则是个体"
        "主动建构“容器”的行为线索。上述解释只描述本次操作动力，不直接等同于病理或稳定人格。"
    )

    scene = _scene_excerpt(scene_text)
    if scene:
        integrated = (
            f"把过程数据放回场景看：{scene}。若过程呈现快速定型、修改少，而场景又高度封闭，"
            "需要区分“果断成形”与“回避深入探索”；若过程修改多、地形笔触集中在核心区，"
            "则更支持“反复安放核心冲突”的假设。最终仍需用访谈问题区分支持性与防御性解释。"
        )
    else:
        integrated = (
            "过程数据与场景意象需要相互校验：快速定型、低修改可能支持“整体规划较强”，"
            "也可能提示“探索深度有限”；高修改、长停顿既可能反映审慎，也可能反映选择困难。"
            "报告只把它作为探索性假设，不单独据此下结论。"
        )

    evidence = [
        f"总耗时 {duration} 秒，放入 {added} 件，删除/撤回 {deleted} 件，拖拽 {moved} 次，撤销 {undo} 次。",
        f"推沙/挖水 {strokes} 笔，动作总数 {metrics['action_count']} 次。",
    ]
    if long_pause:
        evidence.append(f"8 秒以上停顿 {long_pause} 次，最长 {longest_pause} 秒。")
    if metrics["bury_count"] or metrics["destructive_loops"]:
        evidence.append(f"掩埋人物 {metrics['bury_count']} 次，短时反复放删 {metrics['destructive_loops']} 次。")

    return {
        "available": True,
        "title": "制作过程动力学观察",
        "pace": pace,
        "revision": revision_text,
        "terrain_control": terrain_text,
        "theory_interpretation": theory,
        "integrated_finding": integrated,
        "evidence": evidence,
        "confidence": "中" if duration and added >= 3 else "低",
    }
