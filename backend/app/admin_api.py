from __future__ import annotations

import copy
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .config import COUNSELOR_TOKEN
from .db import get_db
from .models import AdminUser, Assessment, ReportReview, ShareLink
from .utils import iso_utc, new_id

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

ROLE_DEFINITIONS = [
    {
        "key": "super_admin",
        "name": "超级管理员",
        "short": "管理员",
        "description": "管理账号、角色权限、全校数据与系统配置",
        "permissions": ["用户管理", "角色配置", "报告审核", "数据看板"],
    },
    {
        "key": "counselor",
        "name": "心理咨询师",
        "short": "咨询师",
        "description": "审核评估报告、修订建议、生成家长分享二维码",
        "permissions": ["报告审核", "报告修订", "二维码分享"],
    },
    {
        "key": "teacher",
        "name": "班主任",
        "short": "班主任",
        "description": "查看本班测评进度与群体发展画像",
        "permissions": ["班级数据", "训练建议", "脱敏报告"],
    },
    {
        "key": "student",
        "name": "受测学生",
        "short": "学生",
        "description": "参与沙盘测评并查看自己的发展性报告",
        "permissions": ["沙盘测评", "个人报告", "训练任务"],
    },
]

SEED_USERS = [
    {
        "name": "林知远",
        "account": "lin.zhiyuan",
        "role_key": "super_admin",
        "department": "平台管理中心",
        "grade_level": "",
        "class_name": "",
        "student_no": "",
    },
    {
        "name": "沈岚",
        "account": "shen.lan",
        "role_key": "counselor",
        "department": "心理发展中心",
        "grade_level": "",
        "class_name": "",
        "student_no": "",
    },
    {
        "name": "陈语",
        "account": "chen.yu",
        "role_key": "counselor",
        "department": "心理发展中心",
        "grade_level": "",
        "class_name": "",
        "student_no": "",
    },
    {
        "name": "王珊",
        "account": "wang.shan",
        "role_key": "teacher",
        "department": "初中部",
        "grade_level": "初二",
        "class_name": "3 班",
        "student_no": "",
    },
    {
        "name": "赵明",
        "account": "zhao.ming",
        "role_key": "teacher",
        "department": "初中部",
        "grade_level": "初一",
        "class_name": "1 班",
        "student_no": "",
    },
    {
        "name": "周禾",
        "account": "zhou.he",
        "role_key": "teacher",
        "department": "高中部",
        "grade_level": "高一",
        "class_name": "2 班",
        "student_no": "",
    },
    {
        "name": "李瑶",
        "account": "li.yao",
        "role_key": "student",
        "department": "初中部",
        "grade_level": "初二",
        "class_name": "3 班",
        "student_no": "PS-QUICK",
    },
    {
        "name": "顾南",
        "account": "gu.nan",
        "role_key": "student",
        "department": "初中部",
        "grade_level": "初一",
        "class_name": "1 班",
        "student_no": "PS-2026-018",
    },
    {
        "name": "陆遥",
        "account": "lu.yao",
        "role_key": "student",
        "department": "高中部",
        "grade_level": "高一",
        "class_name": "2 班",
        "student_no": "PS-2026-023",
        "status": "disabled",
    },
]


def require_admin(
    x_counselor_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> None:
    token = x_counselor_token or ""
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token or token != COUNSELOR_TOKEN:
        raise HTTPException(status_code=401, detail="咨询师后台令牌无效")


def ensure_admin_seed(db: Session) -> None:
    if db.query(AdminUser).count():
        return
    for item in SEED_USERS:
        db.add(
            AdminUser(
                id=new_id(),
                name=item["name"],
                account=item["account"],
                role_key=item["role_key"],
                department=item.get("department", ""),
                grade_level=item.get("grade_level", ""),
                class_name=item.get("class_name", ""),
                student_no=item.get("student_no", ""),
                status=item.get("status", "active"),
            )
        )
    db.commit()


def _ok(request: Request, data: Any, message: str = "success") -> dict[str, Any]:
    return {
        "code": "OK",
        "message": message,
        "data": data,
        "trace_id": request.headers.get("X-Request-Id") or f"req_{new_id()[:20]}",
    }


def _role_payload() -> list[dict[str, Any]]:
    return ROLE_DEFINITIONS


def _user_payload(user: AdminUser) -> dict[str, Any]:
    role = next((item for item in ROLE_DEFINITIONS if item["key"] == user.role_key), None)
    return {
        "user_id": user.id,
        "name": user.name,
        "account": user.account,
        "role_key": user.role_key,
        "role_name": role["name"] if role else user.role_key,
        "role_short": role["short"] if role else user.role_key,
        "department": user.department,
        "grade_level": user.grade_level,
        "class_name": user.class_name,
        "student_no": user.student_no,
        "status": user.status,
        "created_at": iso_utc(user.created_at),
        "updated_at": iso_utc(user.updated_at),
    }


def _parse_json_object(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _load_report(row: Assessment) -> dict[str, Any]:
    if not row.report_json:
        return {}
    try:
        value = json.loads(row.report_json)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


EDITABLE_REPORT_SECTIONS = {
    "chapter_2_imagery": "第二章 · 探索性假设与核验问题",
    "chapter_6_interview": "第六章 · 访谈问题",
    "chapter_9_general_advice": "第九章 · 总体建议",
}


def _parse_date(value: str, end_of_day: bool = False) -> datetime | None:
    value = str(value or "").strip()
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None
    return parsed + timedelta(days=1) if end_of_day else parsed


def _filtered_assessments(
    db: Session,
    *,
    school: str = "",
    class_name: str = "",
    grade: str = "",
    date_from: str = "",
    date_to: str = "",
):
    query = db.query(Assessment).filter(Assessment.report_json.isnot(None))
    if school.strip():
        query = query.filter(Assessment.school_name == school.strip())
    if class_name.strip():
        query = query.filter(Assessment.class_name == class_name.strip())
    if grade.strip():
        query = query.filter(Assessment.grade_level == grade.strip())
    start = _parse_date(date_from)
    if start:
        query = query.filter(Assessment.created_at >= start)
    end = _parse_date(date_to, end_of_day=True)
    if end:
        query = query.filter(Assessment.created_at < end)
    return query


def _extract_editable_sections(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="报告修订内容必须是 JSON 对象")
    sections: dict[str, Any] = {}
    for key in EDITABLE_REPORT_SECTIONS:
        value = payload.get(key)
        if isinstance(value, dict):
            sections[key] = value
    if not sections:
        raise HTTPException(status_code=422, detail="未提交可编辑章节（第二、六、九章）")
    return sections


def _merge_editable_report(
    original: dict[str, Any],
    draft_sections: dict[str, Any],
    *,
    reviewer_id: str | None,
    revision: int,
    applied_at: str,
) -> dict[str, Any]:
    merged = copy.deepcopy(original)
    for key, value in draft_sections.items():
        if key in EDITABLE_REPORT_SECTIONS:
            merged[key] = copy.deepcopy(value)
    meta = merged.setdefault("meta", {})
    meta["review_edited"] = True
    meta["review_edited_sections"] = [key for key in EDITABLE_REPORT_SECTIONS if key in draft_sections]
    meta["review_revision"] = revision
    meta["review_applied_at"] = applied_at
    meta["reviewer_id"] = reviewer_id or ""
    return merged


def _review_payload(review: ReportReview | None) -> dict[str, Any]:
    return {
        "status": review.status if review else "pending",
        "note": review.note if review else "",
        "reviewer_id": review.reviewer_id if review else None,
        "draft_note": review.draft_note if review else "",
        "has_draft": bool(review and review.draft_report_json) if review else False,
        "draft_updated_at": iso_utc(review.draft_updated_at) if review and review.draft_updated_at else None,
        "review_applied_at": iso_utc(review.review_applied_at) if review and review.review_applied_at else None,
        "updated_at": iso_utc(review.updated_at) if review else None,
    }


def _risk_rank(level: str | None) -> int:
    match = re.search(r"L(\d)", str(level or "").upper())
    return int(match.group(1)) if match else 1


def _highest_risk(report: dict[str, Any]) -> str:
    levels = []
    banner = report.get("priority_banner") or {}
    banner_level = str(banner.get("level") or "").upper()
    banner_match = re.search(r"L(\d)", banner_level)
    if banner_match:
        levels.append(f"L{banner_match.group(1)}")
    dimensions = ((report.get("chapter_5_risk") or {}).get("dimensions") or [])
    for item in dimensions:
        if isinstance(item, dict):
            levels.append(str(item.get("level") or "L1").upper())
    if not levels:
        return "L1"
    return max(levels, key=_risk_rank)


def _report_brief(row: Assessment, review: ReportReview | None, active_shares: int) -> dict[str, Any]:
    report = _load_report(row)
    meta = report.get("meta") or {}
    return {
        "assessment_id": row.id,
        "report_no": meta.get("report_no") or f"PS-{row.id[:8].upper()}",
        "student_name": row.student_name or "匿名受测者",
        "student_no": row.student_no,
        "grade_level": row.grade_level,
        "gender": row.gender,
        "school_name": getattr(row, "school_name", "") or "",
        "class_name": getattr(row, "class_name", "") or "",
        "seat_no": getattr(row, "seat_no", "") or "",
        "contact_phone": getattr(row, "contact_phone", "") or "",
        "academic_scores": _parse_json_object(getattr(row, "academic_scores_json", "{}")),
        "representative_item_name": row.representative_item_name,
        "self_image": getattr(row, "self_image", "") or "",
        "self_image_note": getattr(row, "self_image_note", "") or "",
        "created_at": iso_utc(row.created_at),
        "updated_at": iso_utc(row.updated_at),
        "report_revision": int(getattr(row, "report_revision", 0) or 0),
        "generation_status": row.status,
        "engine": row.report_engine,
        "demo_report": str(row.report_engine or "").lower() == "demo",
        "risk_level": _highest_risk(report),
        "review_status": review.status if review else "pending",
        "review_note": review.note if review else "",
        "has_review_draft": bool(review and review.draft_report_json),
        "share_count": active_shares,
        "chapter_count": len([key for key in report.keys() if key.startswith("chapter_")]),
    }


@router.get("/bootstrap")
async def bootstrap(request: Request, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    ensure_admin_seed(db)
    rows = db.query(Assessment).filter(Assessment.report_json.isnot(None)).order_by(Assessment.created_at.desc()).all()
    pending = 0
    for row in rows:
        review = db.get(ReportReview, row.id)
        if not review or review.status in {"pending", "changes"}:
            pending += 1
    users = db.query(AdminUser).order_by(AdminUser.created_at.asc()).all()
    return _ok(
        request,
        {
            "system": {
                "name": "心理沙盘发展性评估管理后台",
                "school": "中科青行 · 学校心理发展中心",
                "version": "2026.11",
            },
            "roles": _role_payload(),
            "users": [_user_payload(item) for item in users],
            "counts": {
                "users": len(users),
                "reports": len(rows),
                "pending_reviews": pending,
            },
        },
    )


@router.get("/users")
async def list_users(
    request: Request,
    q: str = "",
    role: str = "all",
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    ensure_admin_seed(db)
    query = db.query(AdminUser)
    if q.strip():
        keyword = f"%{q.strip()}%"
        query = query.filter(
            or_(
                AdminUser.name.like(keyword),
                AdminUser.account.like(keyword),
                AdminUser.department.like(keyword),
                AdminUser.student_no.like(keyword),
            )
        )
    if role and role != "all":
        query = query.filter(AdminUser.role_key == role)
    users = query.order_by(AdminUser.created_at.asc()).all()
    return _ok(request, {"users": [_user_payload(item) for item in users], "total": len(users)})


@router.post("/users")
async def create_user(request: Request, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    body = await request.json()
    name = str(body.get("name") or "").strip()
    account = str(body.get("account") or "").strip()
    role_key = str(body.get("role_key") or "").strip()
    if not name or not account:
        raise HTTPException(status_code=422, detail="姓名与账号不能为空")
    if role_key not in {item["key"] for item in ROLE_DEFINITIONS}:
        raise HTTPException(status_code=422, detail="角色无效")
    if db.query(AdminUser).filter(AdminUser.account == account).first():
        raise HTTPException(status_code=409, detail="该账号已存在")
    user = AdminUser(
        id=new_id(),
        name=name,
        account=account,
        role_key=role_key,
        department=str(body.get("department") or "").strip(),
        grade_level=str(body.get("grade_level") or "").strip(),
        class_name=str(body.get("class_name") or "").strip(),
        student_no=str(body.get("student_no") or "").strip(),
        status=str(body.get("status") or "active").strip(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _ok(request, {"user": _user_payload(user)}, "用户已创建")


@router.patch("/users/{user_id}")
async def update_user(
    request: Request,
    user_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    user = db.get(AdminUser, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    body = await request.json()
    if "name" in body and str(body["name"]).strip():
        user.name = str(body["name"]).strip()
    if "account" in body:
        account = str(body["account"]).strip()
        if account and account != user.account and db.query(AdminUser).filter(AdminUser.account == account).first():
            raise HTTPException(status_code=409, detail="该账号已存在")
        user.account = account or user.account
    if "role_key" in body:
        role_key = str(body["role_key"]).strip()
        if role_key not in {item["key"] for item in ROLE_DEFINITIONS}:
            raise HTTPException(status_code=422, detail="角色无效")
        user.role_key = role_key
    for field in ("department", "grade_level", "class_name", "student_no", "status"):
        if field in body:
            setattr(user, field, str(body[field] or "").strip())
    if user.status not in {"active", "disabled"}:
        raise HTTPException(status_code=422, detail="用户状态无效")
    db.commit()
    db.refresh(user)
    return _ok(request, {"user": _user_payload(user)}, "用户已更新")


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, request: Request, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    user = db.get(AdminUser, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    db.delete(user)
    db.commit()
    return _ok(request, {"user_id": user_id, "deleted": True}, "用户已删除")


@router.get("/reports")
async def list_reports(
    request: Request,
    q: str = "",
    status: str = "all",
    school: str = "",
    class_name: str = "",
    grade: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 100,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    query = _filtered_assessments(
        db,
        school=school,
        class_name=class_name,
        grade=grade,
        date_from=date_from,
        date_to=date_to,
    )
    rows = query.order_by(Assessment.created_at.desc()).all()
    items = []
    all_schools = set()
    all_classes = set()
    all_grades = set()
    for row in rows:
        all_schools.add(getattr(row, "school_name", "") or "未填写")
        all_classes.add(getattr(row, "class_name", "") or "未填写")
        all_grades.add(row.grade_level or "未填写")
        review = db.get(ReportReview, row.id)
        shares = db.query(ShareLink).filter(ShareLink.assessment_id == row.id, ShareLink.revoked.is_(False)).count()
        brief = _report_brief(row, review, shares)
        if status and status != "all" and brief["review_status"] != status:
            continue
        if q.strip():
            keyword = q.strip().lower()
            haystack = " ".join(
                [
                    brief["student_name"],
                    brief["student_no"],
                    brief["report_no"],
                    brief["representative_item_name"],
                    brief["school_name"],
                    brief["class_name"],
                    brief["seat_no"],
                ]
            ).lower()
            if keyword not in haystack:
                continue
        items.append(brief)
    limited = items[: max(1, min(limit, 200))]
    return _ok(
        request,
        {
            "reports": limited,
            "total": len(items),
            "filters": {
                "school": school,
                "class_name": class_name,
                "grade": grade,
                "date_from": date_from,
                "date_to": date_to,
            },
            "facets": {
                "schools": sorted(all_schools),
                "classes": sorted(all_classes),
                "grades": sorted(all_grades),
            },
        },
    )


@router.get("/reports/{assessment_id}/review-context")
async def report_review_context(
    request: Request,
    assessment_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    row = db.get(Assessment, assessment_id)
    if not row or not row.report_json:
        raise HTTPException(status_code=404, detail="报告不存在或尚未生成")
    review = db.get(ReportReview, assessment_id)
    effective = _load_report(row)
    ai_report = effective
    if review and review.ai_report_json:
        try:
            ai_report = json.loads(review.ai_report_json)
        except Exception:
            ai_report = effective
    draft_sections: dict[str, Any] = {}
    if review and review.draft_report_json:
        try:
            draft_sections = _extract_editable_sections(json.loads(review.draft_report_json))
        except Exception:
            draft_sections = {}
    preview = _merge_editable_report(
        ai_report,
        draft_sections,
        reviewer_id=review.reviewer_id if review else None,
        revision=int(getattr(row, "report_revision", 0) or 0) + (1 if draft_sections else 0),
        applied_at="",
    ) if draft_sections else effective
    return _ok(
        request,
        {
            "assessment_id": assessment_id,
            "report_revision": int(getattr(row, "report_revision", 0) or 0),
            "review": _review_payload(review),
            "editable_sections": [
                {"key": key, "label": label} for key, label in EDITABLE_REPORT_SECTIONS.items()
            ],
            "ai_report": ai_report,
            "effective_report": effective,
            "draft_sections": draft_sections,
            "preview_report": preview,
        },
    )


@router.put("/reports/{assessment_id}/review-draft")
async def save_review_draft(
    request: Request,
    assessment_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    row = db.get(Assessment, assessment_id)
    if not row or not row.report_json:
        raise HTTPException(status_code=404, detail="报告不存在或尚未生成")
    body = await request.json()
    draft = _extract_editable_sections(body.get("draft") or body.get("report") or {})
    review = db.get(ReportReview, assessment_id)
    if not review:
        review = ReportReview(assessment_id=assessment_id)
        db.add(review)
    if not review.ai_report_json:
        review.ai_report_json = row.report_json
    review.draft_report_json = json.dumps(draft, ensure_ascii=False)
    review.draft_note = str(body.get("note") or "").strip()
    review.draft_updated_at = datetime.utcnow()
    review.reviewer_id = str(body.get("reviewer_id") or review.reviewer_id or "").strip() or None
    if review.status in {"pending", "approved"}:
        review.status = "changes"
    db.commit()
    db.refresh(review)
    return _ok(
        request,
        {
            "assessment_id": assessment_id,
            "review": _review_payload(review),
            "draft_sections": draft,
        },
        "报告修订草稿已保存",
    )


@router.post("/reports/{assessment_id}/review")
async def review_report(
    request: Request,
    assessment_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    row = db.get(Assessment, assessment_id)
    if not row or not row.report_json:
        raise HTTPException(status_code=404, detail="报告不存在或尚未生成")
    body = await request.json()
    status = str(body.get("status") or "pending").strip()
    if status not in {"pending", "changes", "approved", "rejected"}:
        raise HTTPException(status_code=422, detail="审核状态无效")
    review = db.get(ReportReview, assessment_id)
    if not review:
        review = ReportReview(assessment_id=assessment_id)
        db.add(review)
    if not review.ai_report_json:
        review.ai_report_json = row.report_json

    submitted_draft = body.get("draft") or body.get("report")
    if submitted_draft:
        draft_sections = _extract_editable_sections(submitted_draft)
        review.draft_report_json = json.dumps(draft_sections, ensure_ascii=False)
        review.draft_updated_at = datetime.utcnow()
    draft_sections = {}
    if review.draft_report_json:
        try:
            draft_sections = _extract_editable_sections(json.loads(review.draft_report_json))
        except Exception:
            draft_sections = {}

    review.status = status
    review.note = str(body.get("note") or "").strip()
    review.reviewer_id = str(body.get("reviewer_id") or "").strip() or None

    if status == "approved" and draft_sections:
        original = _load_report(row)
        revision = int(getattr(row, "report_revision", 0) or 0) + 1
        applied_at = iso_utc(datetime.utcnow())
        effective = _merge_editable_report(
            original,
            draft_sections,
            reviewer_id=review.reviewer_id,
            revision=revision,
            applied_at=applied_at,
        )
        row.report_json = json.dumps(effective, ensure_ascii=False)
        row.report_revision = revision
        review.review_applied_at = datetime.utcnow()
        review.draft_report_json = None
    db.commit()
    db.refresh(review)
    db.refresh(row)
    return _ok(
        request,
        {
            "assessment_id": assessment_id,
            "status": review.status,
            "note": review.note,
            "reviewer_id": review.reviewer_id,
            "report_revision": int(getattr(row, "report_revision", 0) or 0),
            "review": _review_payload(review),
            "updated_at": iso_utc(review.updated_at),
        },
        "审核状态已保存",
    )


def _grid_label(key: str) -> str:
    return {
        "top_left": "左上",
        "top_center": "上中",
        "top_right": "右上",
        "middle_left": "左中",
        "center": "中心",
        "middle_right": "右中",
        "bottom_left": "左下",
        "bottom_center": "下中",
        "bottom_right": "右下",
    }.get(key, key)


def _parse_items(row: Assessment) -> list[dict[str, Any]]:
    try:
        value = json.loads(row.items_json or "[]")
        return value if isinstance(value, list) else []
    except Exception:
        return []


def _parse_grid(row: Assessment) -> dict[str, int]:
    try:
        value = json.loads(row.grid_distribution_json or "{}")
    except Exception:
        value = {}
    counts: dict[str, int] = defaultdict(int)
    cells = value.get("cells") if isinstance(value, dict) else None
    if isinstance(cells, list):
        for cell in cells:
            if not isinstance(cell, dict):
                continue
            key = str(cell.get("key") or "")
            counts[_grid_label(key)] += int(cell.get("count") or 0)
    if not counts:
        for item in _parse_items(row):
            counts[_grid_label(str(item.get("grid_key") or "center"))] += 1
    return dict(counts)


@router.get("/stats")
async def admin_stats(
    request: Request,
    school: str = "",
    class_name: str = "",
    grade: str = "",
    date_from: str = "",
    date_to: str = "",
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    rows = _filtered_assessments(
        db,
        school=school,
        class_name=class_name,
        grade=grade,
        date_from=date_from,
        date_to=date_to,
    ).order_by(Assessment.created_at.desc()).all()
    risk_counts = Counter({"L1": 0, "L2": 0, "L3": 0, "L4": 0})
    high_risk = []
    item_counts: Counter[str] = Counter()
    item_categories: Counter[str] = Counter()
    grid_counts: Counter[str] = Counter()
    module_counts: Counter[str] = Counter()
    grade_counts: Counter[str] = Counter()
    school_counts: Counter[str] = Counter()
    class_counts: Counter[str] = Counter()
    total_items = 0

    for row in rows:
        report = _load_report(row)
        level = _highest_risk(report)
        risk_counts[level] += 1
        if _risk_rank(level) >= 2:
            high_risk.append(
                {
                    "assessment_id": row.id,
                    "student_name": row.student_name or "匿名受测者",
                    "grade_level": row.grade_level,
                    "risk_level": level,
                    "created_at": iso_utc(row.created_at),
                }
            )
        grade_counts[row.grade_level or "未填写"] += 1
        school_counts[getattr(row, "school_name", "") or "未填写"] += 1
        class_counts[getattr(row, "class_name", "") or "未填写"] += 1

        items = _parse_items(row)
        total_items += len(items)
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("label") or item.get("name") or item.get("item_name") or "未命名沙具")
            item_counts[name] += 1
            category = str(item.get("category") or "其他")
            item_categories[category] += 1

        for label, count in _parse_grid(row).items():
            grid_counts[label] += count

        modules = ((report.get("chapter_8_training_modules") or {}).get("modules") or [])
        seen = set()
        for module in modules:
            if not isinstance(module, dict):
                continue
            name = str(module.get("name") or "").strip()
            if name and name not in seen:
                seen.add(name)
                module_counts[name] += 1
        if not seen:
            for dimension in ((report.get("chapter_3_six_dimensions") or {}).get("dimensions") or []):
                if not isinstance(dimension, dict):
                    continue
                for direction in dimension.get("training_module_directions") or []:
                    match = re.search(r"模块[一二三四五六七八九十]+[^，。；]*", str(direction))
                    if match:
                        name = match.group(0).strip()
                        if name not in seen:
                            seen.add(name)
                            module_counts[name] += 1

    pending = 0
    approved = 0
    for row in rows:
        review = db.get(ReportReview, row.id)
        if not review or review.status in {"pending", "changes"}:
            pending += 1
        elif review.status == "approved":
            approved += 1

    assessment_ids = [row.id for row in rows]
    share_count = 0
    if assessment_ids:
        share_count = (
            db.query(ShareLink)
            .filter(ShareLink.revoked.is_(False), ShareLink.assessment_id.in_(assessment_ids))
            .count()
        )
    high_risk.sort(key=lambda item: (_risk_rank(item["risk_level"]), item["created_at"]), reverse=True)

    return _ok(
        request,
        {
            "summary": {
                "total_reports": len(rows),
                "pending_reviews": pending,
                "approved_reports": approved,
                "high_risk_reports": len(high_risk),
                "share_links": share_count,
                "total_items": total_items,
                "sample_sufficient": len(rows) >= 5,
            },
            "risk_distribution": [
                {"level": "L1", "label": "L1 平稳", "value": risk_counts["L1"]},
                {"level": "L2", "label": "L2 轻度关注", "value": risk_counts["L2"]},
                {"level": "L3", "label": "L3 中度关注", "value": risk_counts["L3"]},
                {"level": "L4", "label": "L4 重点关注", "value": risk_counts["L4"]},
            ],
            "high_risk_students": high_risk[:8],
            "top_items": [
                {"name": name, "value": count}
                for name, count in item_counts.most_common(20)
            ],
            "item_categories": [
                {"name": name, "value": count}
                for name, count in item_categories.most_common(8)
            ],
            "grid_heatmap": [
                {"label": label, "value": grid_counts.get(label, 0)}
                for label in ["左上", "上中", "右上", "左中", "中心", "右中", "左下", "下中", "右下"]
            ],
            "module_distribution": [
                {"name": name, "value": count}
                for name, count in module_counts.most_common(6)
            ],
            "grade_distribution": [
                {"name": name, "value": count}
                for name, count in grade_counts.most_common()
            ],
            "class_distribution": [
                {"name": name, "value": count}
                for name, count in class_counts.most_common()
            ],
            "school_distribution": [
                {"name": name, "value": count}
                for name, count in school_counts.most_common()
            ],
            "scope": {
                "school": school,
                "class_name": class_name,
                "grade": grade,
                "date_from": date_from,
                "date_to": date_to,
                "total_reports": len(rows),
            },
        },
    )
