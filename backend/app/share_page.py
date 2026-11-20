from __future__ import annotations

import html
import json
from typing import Any


def _e(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _list(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    return "".join(f"<li>{_e(x)}</li>" for x in value)


def _paragraphs(value: Any) -> str:
    if isinstance(value, list):
        return "<br>".join(_e(x) for x in value)
    return _e(value)


def render_public_share(report: dict[str, Any], share_token: str) -> str:
    meta = report.get("meta") or {}
    banner = report.get("priority_banner") or {}
    guard = report.get("share_guard") or {}
    if guard.get("blocked") or "L4" in str(banner.get("level") or "").upper():
        title = _e(meta.get("student_name") or "学生")
        return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>心理沙盘评估 · 沟通安排</title>
<style>
:root{{--ink:#24332d;--muted:#6f7a73;--line:#dfe4dc}}
*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;display:grid;place-items:center;padding:28px 18px;background:linear-gradient(160deg,#eef1e8,#f8f5ed 45%,#e4ece8);color:var(--ink);font-family:"Noto Sans SC","PingFang SC","Microsoft YaHei",sans-serif;line-height:1.8}}
.card{{width:min(560px,100%);padding:40px 34px 30px;text-align:center;background:rgba(255,255,255,.86);border:1px solid var(--line);border-radius:22px;box-shadow:0 18px 48px rgba(55,50,40,.09)}}
.mark{{width:58px;height:58px;margin:0 auto 18px;display:grid;place-items:center;border:1px solid #d9c6a5;border-radius:50%;background:#fbf4e7;color:#8a6a3d;font-family:serif;font-size:24px}}
h1{{margin:0;font-size:24px;font-weight:600;letter-spacing:.04em}}p{{margin:14px 0 0;color:#5f6c64;font-size:14px;text-align:left}}
.note{{margin-top:24px;padding-top:18px;border-top:1px solid var(--line);color:var(--muted);font-size:12px;text-align:center}}
</style></head>
<body><div class="card">
<div class="mark">心</div>
<h1>{_e(guard.get('title') or '由心理老师优先一对一沟通')}</h1>
<p>{_e(guard.get('message') or '这份沙盘作品需要心理老师先与家长和孩子进行一对一沟通。沟通完成后，老师会根据家庭与孩子的实际需要，提供更合适的支持建议。')}</p>
<p class="note">{_e(guard.get('note') or '报告内容暂不在本页展示。')}如已收到心理老师联系，请按约定时间沟通即可。</p>
</div></body></html>"""

    ch1 = report.get("chapter_1_overview") or {}
    ch2 = report.get("chapter_2_imagery") or {}
    ch3 = report.get("chapter_3_six_dimensions") or {}
    ch4 = report.get("chapter_4_academic") or {}
    ch6 = report.get("chapter_6_interview") or {}
    ch7 = report.get("chapter_7_career") or {}
    ch8 = report.get("chapter_8_training_modules") or {}
    ch9 = report.get("chapter_9_general_advice") or {}

    category_html = "".join(
        f'<div class="chip">{_e(row.get("category"))}<b>{_e(row.get("count"))}</b></div>'
        for row in (ch1.get("item_category_stats") or [])
        if isinstance(row, dict)
    )
    imagery_rows = "".join(
        f"<tr><td>{_e(row.get('theme'))}</td><td>{_e('、'.join(row.get('symbols') or []))}</td>"
        f"<td>{_e(row.get('hypothesis'))}<div class='muted'>{_e(row.get('theory_basis'))}</div></td></tr>"
        for row in (ch2.get("themes") or [])
        if isinstance(row, dict)
    )
    dimension_html = "".join(
        f"""<article class="card">
          <div class="card-head"><h3>{_e(row.get('name'))}</h3><span class="pill">{_e(row.get('confidence'))}置信度</span></div>
          <p><b>判定建议：</b>{_e(row.get('judgement'))}</p>
          <p><b>评估结果：</b>{_e(row.get('assessment_result'))}</p>
          <div class="muted"><b>评估理论：</b>{_e(row.get('assessment_theory'))}</div>
          <div class="two"><div><b>佐证要点</b><ul>{_list(row.get('evidence'))}</ul></div>
          <div><b>待提升能力</b><ul>{_list(row.get('capabilities_to_improve'))}</ul></div></div>
          <p><b>训练模块：</b>{_e('、'.join(row.get('training_module_directions') or []))}</p>
          <p class="conclusion">{_e(row.get('conclusion'))}</p>
        </article>"""
        for row in (ch3.get("dimensions") or []) if isinstance(row, dict)
    )
    subject_rows = "".join(
        f"<tr><td>{_e(row.get('subject'))}</td><td>{_e(row.get('full_score'))}</td><td>{_e(row.get('score'))}</td>"
        f"<td>{'' if row.get('rate') is None else f'{float(row.get('rate')):.1%}'}</td><td>{_e(row.get('grade'))}</td></tr>"
        for row in (ch4.get("subjects") or []) if isinstance(row, dict)
    )
    interview_rows = "".join(
        f"<tr><td>{_e(row.get('topic'))}</td><td>{_e('；'.join(row.get('questions') or []))}</td><td>{_e(row.get('target'))}</td></tr>"
        for row in (ch6.get("items") or []) if isinstance(row, dict)
    )
    module_html = "".join(
        f"""<article class="card module">
          <div class="card-head"><h3>{_e(row.get('name'))}</h3></div>
          <p><b>训练目标：</b>{_e('、'.join(row.get('goals') or []))}</p>
          <p><b>对应维度：</b>{_e('、'.join(row.get('dimensions') or []))}</p>
          <p><b>训练逻辑：</b>{_e(row.get('logic'))}</p>
          <p><b>开展形式：</b>{_e(row.get('format'))}</p>
          <div class="two"><div><b>老师做什么</b><ul>{_list(row.get('teacher_actions'))}</ul></div>
          <div><b>家长做什么</b><ul>{_list(row.get('parent_actions'))}</ul></div></div>
          <div><b>学生做什么</b><ul>{_list(row.get('student_actions'))}</ul></div>
        </article>"""
        for row in (ch8.get("modules") or []) if isinstance(row, dict)
    )

    career_title = ch7.get("title") or (
        "内在心理资源与保护性因素"
        if ch7.get("career_postponed") is True or "保护性因素" in str(ch7.get("title") or "")
        else "职业发展优势"
    )

    title = _e(meta.get("student_name") or "学生")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>心理沙盘发展性评估报告 · {title}</title>
<style>
:root{{--ink:#24332d;--muted:#6f7a73;--line:#dfe4dc;--paper:#fbfaf6;--accent:#7b5b3d;--green:#4e7462}}
*{{box-sizing:border-box}}body{{margin:0;background:linear-gradient(160deg,#eef1e8,#f8f5ed 45%,#e4ece8);color:var(--ink);font-family:"Noto Sans SC","PingFang SC","Microsoft YaHei",sans-serif;line-height:1.7}}
.wrap{{max-width:1080px;margin:0 auto;padding:36px 20px 70px}}
.top{{display:flex;justify-content:space-between;gap:20px;align-items:flex-start;border-bottom:1px solid var(--line);padding-bottom:22px;margin-bottom:28px}}
h1{{font-size:28px;letter-spacing:.08em;margin:0 0 8px;font-weight:600}}h2{{font-size:19px;letter-spacing:.1em;margin:36px 0 14px;padding-left:12px;border-left:3px solid var(--accent)}}
h3{{font-size:15px;margin:0;font-weight:600}}.muted{{color:var(--muted);font-size:13px}}.meta{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:14px;font-size:13px}}
.meta div{{background:rgba(255,255,255,.7);border:1px solid var(--line);border-radius:10px;padding:8px 10px}}.badge{{font-size:12px;padding:6px 12px;border-radius:999px;background:#e8efe8;color:var(--green);white-space:nowrap}}
.card{{background:rgba(255,255,255,.78);border:1px solid var(--line);border-radius:16px;padding:18px;margin:12px 0;box-shadow:0 8px 28px rgba(55,50,40,.05)}}
.card-head{{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:10px}}.pill{{font-size:12px;color:var(--accent);background:#f5ede2;border-radius:999px;padding:3px 10px}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}.chips{{display:flex;flex-wrap:wrap;gap:8px}}.chip{{border:1px solid var(--line);background:#fff;border-radius:8px;padding:5px 10px;font-size:12px}}.chip b{{color:var(--accent);margin-left:8px}}
table{{width:100%;border-collapse:collapse;background:rgba(255,255,255,.8);border-radius:12px;overflow:hidden;font-size:13px}}th,td{{padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:top;text-align:left}}th{{background:#f0f2ec;color:#536158;font-weight:500}}
.hero{{display:grid;grid-template-columns:minmax(260px,420px) 1fr;gap:24px;align-items:start}}.shot{{width:100%;border-radius:14px;border:1px solid var(--line);display:block;background:#fff}}
.conclusion{{background:#f7f2e8;border-left:3px solid var(--accent);padding:8px 12px;border-radius:0 8px 8px 0}}.notice{{margin-top:28px;border:1px solid #e8dcc8;background:#fffaf0;border-radius:14px;padding:16px;font-size:13px;color:#715b45}}
.module ul{{margin:6px 0 10px 18px}}li{{margin:2px 0}}ul{{margin:4px 0 10px 18px}}
@media(max-width:760px){{.meta,.two,.hero{{grid-template-columns:1fr}}.top{{display:block}}h1{{font-size:23px}}table{{display:block;overflow:auto}}}}
</style></head>
<body><div class="wrap">
<header class="top"><div><h1>心理沙盘发展性评估报告</h1><div class="muted">发展性心理评估参考 · 非临床诊断</div>
<div class="meta">
<div>受测者：{_e(meta.get('student_name') or '匿名受测者')}</div><div>年级段：{_e(meta.get('grade_level'))}</div><div>性别：{_e(meta.get('gender'))}</div>
<div>报告编号：{_e(meta.get('report_no'))}</div><div>生成时间：{_e(meta.get('generated_at'))}</div><div>查看版本：家长 / 学生端</div>
</div></div><div class="badge">分享查看 · 内部研判内容已隐藏</div></header>

<h2>一、整体结果与场景概览</h2>
<div class="hero">
<div>{f'<img class="shot" src="{_e(ch1.get("sandplay_image_url"))}" alt="沙盘作品">' if ch1.get('sandplay_image_url') else ''}</div>
<div class="card"><p><b>沙具聚集区：</b>{_e(ch1.get('clusters'))}</p>
<p><b>留白区域：</b>{_e(ch1.get('blank_areas'))}</p>
{ f"<p><b>代表沙具：</b>{_e(ch1.get('representative_item_name'))}</p>" if ch1.get('representative_item_name') else '' }
<p><b>地形观察：</b>{_e(ch1.get('terrain_observation'))}</p>
<div class="chips">{category_html}</div>
<p><b>场景意象：</b></p><ul>{_list(ch1.get('scene_imagery'))}</ul></div></div>

<h2>二、沙盘作品意象分析</h2>
<div class="notice">以下为探索性假设，需访谈确认，非临床诊断。</div>
<table><thead><tr><th>意象主题</th><th>象征沙具</th><th>分析假设</th></tr></thead><tbody>{imagery_rows}</tbody></table>

<h2>三、六维方向判定与训练模块指向</h2>
{dimension_html}

<h2>四、学业成绩与学业评价</h2>
<div class="card"><p><b>整体解读：</b>{_e(ch4.get('overall_interpretation') or ch4.get('overall_interpretation'))}</p>
<p><b>等级标准：</b>{_e(ch4.get('grade_standard'))}</p>
<table><thead><tr><th>科目</th><th>满分</th><th>得分</th><th>得分率</th><th>等级</th></tr></thead><tbody>{subject_rows or '<tr><td colspan="5">本次未提供可读成绩单</td></tr>'}</tbody></table>
<div class="two"><div><b>优势学科</b><p>{_e(ch4.get('strengths'))}</p></div><div><b>待提升学科</b><p>{_e(ch4.get('weaknesses'))}</p></div></div>
<p><b>成绩趋势：</b>{_e(ch4.get('trend'))}</p></div>

<h2>六、访谈建议</h2>
<table><thead><tr><th>访谈话题</th><th>建议提问</th><th>对象</th></tr></thead><tbody>{interview_rows}</tbody></table>

<h2>七、{_e(career_title)}</h2>
<div class="card"><p><b>生涯阶段：</b>{_e(ch7.get('stage'))}</p><p>{_e(ch7.get('summary'))}</p>
<div class="two"><div><b>发展优势</b><ul>{_list(ch7.get('strengths'))}</ul></div><div><b>老师做什么</b><ul>{_list(ch7.get('teacher_actions'))}</ul><b>家长做什么</b><ul>{_list(ch7.get('parent_actions'))}</ul></div></div>
<p><b>学生做什么：</b></p><ul>{_list(ch7.get('student_actions'))}</ul></div>

<h2>八、学习能力训练模块方向建议</h2>
{module_html}

<h2>九、总体使用建议</h2>
<div class="card"><h3>成长型思维：能力训练的底层动力</h3><ul>{_list(ch9.get('growth_mindset'))}</ul>
<h3>优势能力迁移</h3><ul>{_list(ch9.get('strength_transfer'))}</ul>
<h3>以能力发展替代特质判定</h3><ul>{_list(ch9.get('capability_not_label'))}</ul></div>
<div class="notice"><b>免责声明：</b>{_e(ch9.get('disclaimer'))}<br>本页面为学生 / 家长查看版本，服务端已隐藏咨询师内部研判内容；所有结论均为发展性评估参考，不用于分班、评优或医学诊断。</div>
<footer class="muted" style="margin-top:28px">分享标识 {_e(share_token[:10])}… · 长期有效，可联系咨询师申请撤回</footer>
</div></body></html>"""
