from __future__ import annotations

import copy
import hmac
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .auth import (
    hash_password,
    hash_session_token,
    new_session_token,
    normalise_account,
    validate_password,
    verify_password,
)
from .config import (
    ADMIN_INITIAL_ACCOUNT,
    ADMIN_INITIAL_NAME,
    ADMIN_INITIAL_PASSWORD,
    ADMIN_LOCK_MINUTES,
    ADMIN_MAX_LOGIN_FAILURES,
    ADMIN_SESSION_HOURS,
    COUNSELOR_TOKEN,
    ENABLE_SERVICE_TOKEN,
    SEED_DEMO_USERS,
)
from .db import get_db
from .models import AdminSession, AdminUser, Assessment, ReportReview, ShareLink
from .utils import iso_utc, new_id, sign_report_media

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
workbench_router = APIRouter(prefix="/api/v1/workbench", tags=["workbench"])

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
        "description": "使用学生账号进入沙盘工作台，完成并提交本次沙盘测评",
        "permissions": ["沙盘测评", "作品提交"],
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


@dataclass
class AdminPrincipal:
    user: AdminUser | None
    role_key: str
    is_super_admin: bool
    auth_type: str
    session_id: str = ""


def _extract_auth_token(
    x_counselor_token: str | None,
    authorization: str | None,
) -> str:
    token = str(x_counselor_token or "").strip()
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    return token


def require_admin(
    x_counselor_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> AdminPrincipal:
    token = _extract_auth_token(x_counselor_token, authorization)
    if not token:
        raise HTTPException(status_code=401, detail="请先登录咨询师控制台")

    # 兼容受控运维脚本的服务令牌：必须同时在配置中显式开启，且不再有内置默认值。
    if ENABLE_SERVICE_TOKEN and COUNSELOR_TOKEN and hmac.compare_digest(token, COUNSELOR_TOKEN):
        return AdminPrincipal(
            user=None,
            role_key="super_admin",
            is_super_admin=True,
            auth_type="service_token",
        )

    now = datetime.utcnow()
    session = (
        db.query(AdminSession)
        .filter(AdminSession.token_hash == hash_session_token(token))
        .first()
    )
    if not session or session.revoked_at is not None or session.expires_at <= now:
        raise HTTPException(status_code=401, detail="登录状态已失效，请重新登录")
    user = db.get(AdminUser, session.user_id)
    if not user or user.status != "active":
        raise HTTPException(status_code=401, detail="账号已停用或不存在")
    if user.role_key == "student":
        raise HTTPException(
            status_code=403,
            detail="学生账号请从沙盘工作台进入，不能登录咨询师控制台",
        )
    if not session.last_seen_at or now - session.last_seen_at > timedelta(minutes=5):
        session.last_seen_at = now
        db.commit()
    return AdminPrincipal(
        user=user,
        role_key=user.role_key,
        is_super_admin=user.role_key == "super_admin",
        auth_type="session",
        session_id=session.id,
    )


def require_student(
    authorization: str | None = Header(default=None),
    x_counselor_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> AdminPrincipal:
    """沙盘工作台只接受受测学生账号。"""
    token = _extract_auth_token(x_counselor_token, authorization)
    if not token:
        raise HTTPException(status_code=401, detail="请先登录学生测评入口")
    if hmac.compare_digest(token, COUNSELOR_TOKEN):
        raise HTTPException(
            status_code=403, detail="沙盘工作台仅面向受测学生开放，请使用学生账号登录"
        )
    now = datetime.utcnow()
    session = (
        db.query(AdminSession)
        .filter(AdminSession.token_hash == hash_session_token(token))
        .first()
    )
    if not session or session.revoked_at is not None or session.expires_at <= now:
        raise HTTPException(status_code=401, detail="登录状态已失效，请重新登录")
    user = db.get(AdminUser, session.user_id)
    if not user or user.status != "active":
        raise HTTPException(status_code=401, detail="账号已停用或不存在")
    if user.role_key != "student":
        raise HTTPException(
            status_code=403, detail="沙盘工作台仅面向受测学生开放，请使用学生账号登录"
        )
    if not session.last_seen_at or now - session.last_seen_at > timedelta(minutes=5):
        session.last_seen_at = now
        db.commit()
    return AdminPrincipal(
        user=user,
        role_key=user.role_key,
        is_super_admin=False,
        auth_type="session",
        session_id=session.id,
    )


def require_super_admin(principal: AdminPrincipal = Depends(require_admin)) -> AdminPrincipal:
    if not principal.is_super_admin:
        raise HTTPException(status_code=403, detail="仅超级管理员可管理账号与角色")
    return principal


def require_counselor(principal: AdminPrincipal = Depends(require_admin)) -> AdminPrincipal:
    """个体报告只对咨询师与超级管理员开放，班主任只能查看班级汇总。"""
    if principal.role_key not in {"counselor", "super_admin"}:
        raise HTTPException(status_code=403, detail="班主任账号不可查看个体心理报告")
    return principal


def _create_seed_user(item: dict[str, Any]) -> AdminUser:
    return AdminUser(
        id=new_id(),
        name=item["name"],
        account=normalise_account(item["account"]),
        role_key=item["role_key"],
        department=item.get("department", ""),
        grade_level=item.get("grade_level", ""),
        class_name=item.get("class_name", ""),
        student_no=item.get("student_no", ""),
        status=item.get("status", "active"),
    )


def ensure_admin_seed(db: Session) -> None:
    """只在空库时创建首个管理员；演示账号必须显式开启，避免进入生产库。"""
    users = db.query(AdminUser).order_by(AdminUser.created_at.asc()).all()
    if not users:
        if not ADMIN_INITIAL_PASSWORD:
            raise RuntimeError(
                "首次部署必须配置 ADMIN_INITIAL_PASSWORD，系统不会创建无密码管理员，"
                "也不会自动写入演示账号。"
            )
        db.add(
            _create_seed_user(
                {
                    "name": ADMIN_INITIAL_NAME,
                    "account": ADMIN_INITIAL_ACCOUNT,
                    "role_key": "super_admin",
                    "department": "平台管理中心",
                }
            )
        )
        if SEED_DEMO_USERS:
            for item in SEED_USERS:
                if normalise_account(item["account"]) == normalise_account(ADMIN_INITIAL_ACCOUNT):
                    continue
                db.add(_create_seed_user(item))
        db.commit()
        users = db.query(AdminUser).order_by(AdminUser.created_at.asc()).all()

    # 只为第一位超级管理员建立一次初始密码，其他既有账号需由管理员在后台设置。
    if ADMIN_INITIAL_PASSWORD and users and not any(item.password_hash for item in users):
        super_admin = next(
            (item for item in users if item.role_key == "super_admin"), None
        )
        if super_admin:
            super_admin.password_hash = hash_password(ADMIN_INITIAL_PASSWORD)
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
        "password_set": bool(user.password_hash),
        "last_login_at": iso_utc(user.last_login_at),
        "login_locked": bool(user.locked_until and user.locked_until > datetime.utcnow()),
        "created_at": iso_utc(user.created_at),
        "updated_at": iso_utc(user.updated_at),
    }


def _principal_payload(principal: AdminPrincipal) -> dict[str, Any]:
    if principal.user is not None:
        return _user_payload(principal.user)
    return {
        "user_id": "service-token",
        "name": "系统服务账号",
        "account": "service.token",
        "role_key": "super_admin",
        "role_name": "超级管理员",
        "role_short": "管理员",
        "department": "平台运维",
        "grade_level": "",
        "class_name": "",
        "student_no": "",
        "status": "active",
        "password_set": True,
        "last_login_at": None,
        "login_locked": False,
        "created_at": None,
        "updated_at": None,
    }


async def _authenticate_login(
    request: Request,
    db: Session,
    channel: str,
) -> tuple[AdminUser, AdminSession, str]:
    body = await request.json()
    account = normalise_account(body.get("account"))
    password = str(body.get("password") or "")
    if not account or not password:
        raise HTTPException(status_code=422, detail="请输入账号和密码")

    user = db.query(AdminUser).filter(AdminUser.account == account).first()
    if not user:
        raise HTTPException(status_code=401, detail="账号或密码错误")
    if user.status != "active":
        raise HTTPException(status_code=403, detail="账号已停用，请联系管理员")
    if channel == "workbench" and user.role_key != "student":
        raise HTTPException(
            status_code=403,
            detail="沙盘工作台仅面向受测学生开放，请使用学生账号登录",
        )
    if channel == "admin" and user.role_key == "student":
        raise HTTPException(
            status_code=403,
            detail="学生账号请从沙盘工作台进入，不能登录咨询师控制台",
        )
    now = datetime.utcnow()
    if user.locked_until and user.locked_until > now:
        remaining = int((user.locked_until - now).total_seconds() // 60) + 1
        raise HTTPException(
            status_code=423,
            detail=f"密码错误次数过多，请在 {remaining} 分钟后重试",
        )
    if not user.password_hash:
        raise HTTPException(
            status_code=403,
            detail="该账号尚未设置登录密码，请联系超级管理员",
        )

    if not verify_password(password, user.password_hash):
        user.login_failed_count = int(user.login_failed_count or 0) + 1
        if user.login_failed_count >= ADMIN_MAX_LOGIN_FAILURES:
            user.locked_until = now + timedelta(minutes=ADMIN_LOCK_MINUTES)
            user.login_failed_count = 0
            db.commit()
            raise HTTPException(
                status_code=423,
                detail=f"密码连续错误 {ADMIN_MAX_LOGIN_FAILURES} 次，账号已锁定 {ADMIN_LOCK_MINUTES} 分钟",
            )
        db.commit()
        remaining = max(ADMIN_MAX_LOGIN_FAILURES - user.login_failed_count, 0)
        raise HTTPException(
            status_code=401,
            detail=f"账号或密码错误，还可尝试 {remaining} 次",
        )

    user.login_failed_count = 0
    user.locked_until = None
    user.last_login_at = now
    raw_token = new_session_token()
    session = AdminSession(
        id=new_id(),
        user_id=user.id,
        token_hash=hash_session_token(raw_token),
        created_at=now,
        expires_at=now + timedelta(hours=ADMIN_SESSION_HOURS),
        last_seen_at=now,
        ip_address=str(request.client.host if request.client else "")[:80],
        user_agent=str(request.headers.get("user-agent") or "")[:255],
    )
    db.add(session)
    # 清理过期超过 7 天的会话，避免表持续膨胀。
    db.query(AdminSession).filter(
        AdminSession.expires_at < now - timedelta(days=7)
    ).delete(synchronize_session=False)
    db.commit()
    db.refresh(user)
    return user, session, raw_token


def _login_payload(user: AdminUser, session: AdminSession, raw_token: str) -> dict[str, Any]:
    return {
        "token": raw_token,
        "expires_at": iso_utc(session.expires_at),
        "user": _user_payload(user),
    }


@router.post("/login")
async def admin_login(request: Request, db: Session = Depends(get_db)):
    ensure_admin_seed(db)
    user, session, raw_token = await _authenticate_login(request, db, "admin")
    return _ok(request, _login_payload(user, session, raw_token), "登录成功")


@router.post("/logout")
async def admin_logout(
    request: Request,
    principal: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if principal.session_id:
        session = db.get(AdminSession, principal.session_id)
        if session and session.revoked_at is None:
            session.revoked_at = datetime.utcnow()
            db.commit()
    return _ok(request, {"logged_out": True}, "已退出登录")


@router.get("/me")
async def admin_me(
    request: Request,
    principal: AdminPrincipal = Depends(require_admin),
):
    return _ok(
        request,
        {
            "user": _principal_payload(principal),
            "auth_type": principal.auth_type,
        },
    )


@workbench_router.post("/login")
async def workbench_login(request: Request, db: Session = Depends(get_db)):
    ensure_admin_seed(db)
    user, session, raw_token = await _authenticate_login(request, db, "workbench")
    return _ok(request, _login_payload(user, session, raw_token), "登录成功")


@workbench_router.get("/me")
async def workbench_me(
    request: Request,
    principal: AdminPrincipal = Depends(require_student),
):
    return _ok(
        request,
        {
            "user": _principal_payload(principal),
            "auth_type": principal.auth_type,
        },
    )


@workbench_router.post("/logout")
async def workbench_logout(
    request: Request,
    principal: AdminPrincipal = Depends(require_student),
    db: Session = Depends(get_db),
):
    if principal.session_id:
        session = db.get(AdminSession, principal.session_id)
        if session and session.revoked_at is None:
            session.revoked_at = datetime.utcnow()
            db.commit()
    return _ok(request, {"logged_out": True}, "已退出测评")


@router.post("/me/password")
async def change_own_password(
    request: Request,
    principal: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if principal.user is None:
        raise HTTPException(status_code=403, detail="系统服务令牌不支持修改密码")
    body = await request.json()
    current_password = str(body.get("current_password") or "")
    new_password = str(body.get("new_password") or "")
    error = validate_password(new_password)
    if error:
        raise HTTPException(status_code=422, detail=error)
    if not verify_password(current_password, principal.user.password_hash):
        raise HTTPException(status_code=400, detail="当前密码不正确")
    principal.user.password_hash = hash_password(new_password)
    principal.user.login_failed_count = 0
    principal.user.locked_until = None
    # 修改密码后让该账号的其他登录会话失效，当前会话保持可用。
    for session in db.query(AdminSession).filter(
        AdminSession.user_id == principal.user.id,
        AdminSession.revoked_at.is_(None),
    ).all():
        if session.id != principal.session_id:
            session.revoked_at = datetime.utcnow()
    db.commit()
    return _ok(request, {"changed": True}, "密码已更新")



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
        return sign_report_media(value, row.id) if isinstance(value, dict) else {}
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
async def bootstrap(
    request: Request,
    db: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_admin),
):
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
            "users": [_user_payload(item) for item in users]
            if principal.is_super_admin
            else [],
            "current_user": _principal_payload(principal),
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
    principal: AdminPrincipal = Depends(require_super_admin),
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
async def create_user(
    request: Request,
    db: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_super_admin),
):
    body = await request.json()
    name = str(body.get("name") or "").strip()
    account = normalise_account(body.get("account"))
    role_key = str(body.get("role_key") or "").strip()
    if not name or not account:
        raise HTTPException(status_code=422, detail="姓名与账号不能为空")
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,31}", account):
        raise HTTPException(
            status_code=422,
            detail="账号需为 3-32 位小写字母、数字、点、下划线或短横线",
        )
    if role_key not in {item["key"] for item in ROLE_DEFINITIONS}:
        raise HTTPException(status_code=422, detail="角色无效")
    if db.query(AdminUser).filter(AdminUser.account == account).first():
        raise HTTPException(status_code=409, detail="该账号已存在")
    initial_password = str(body.get("password") or "").strip()
    if initial_password:
        error = validate_password(initial_password)
        if error:
            raise HTTPException(status_code=422, detail=error)
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
        password_hash=hash_password(initial_password) if initial_password else "",
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
    principal: AdminPrincipal = Depends(require_super_admin),
):
    user = db.get(AdminUser, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    body = await request.json()
    if "name" in body and str(body["name"]).strip():
        user.name = str(body["name"]).strip()
    if "account" in body:
        account = normalise_account(body.get("account"))
        if account and account != user.account:
            if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,31}", account):
                raise HTTPException(
                    status_code=422,
                    detail="账号需为 3-32 位小写字母、数字、点、下划线或短横线",
                )
            if db.query(AdminUser).filter(AdminUser.account == account).first():
                raise HTTPException(status_code=409, detail="该账号已存在")
            user.account = account
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


@router.post("/users/{user_id}/password")
async def reset_user_password(
    request: Request,
    user_id: str,
    db: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_super_admin),
):
    user = db.get(AdminUser, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    body = await request.json()
    password = str(body.get("password") or "").strip()
    error = validate_password(password)
    if error:
        raise HTTPException(status_code=422, detail=error)
    user.password_hash = hash_password(password)
    user.login_failed_count = 0
    user.locked_until = None
    for session in db.query(AdminSession).filter(
        AdminSession.user_id == user.id,
        AdminSession.revoked_at.is_(None),
    ).all():
        if session.id != principal.session_id:
            session.revoked_at = datetime.utcnow()
    db.commit()
    return _ok(
        request,
        {"user": _user_payload(user)},
        "密码已设置，该账号原有登录会话已失效",
    )


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_super_admin),
):
    user = db.get(AdminUser, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if principal.user is not None and principal.user.id == user.id:
        raise HTTPException(status_code=409, detail="不能删除当前登录账号")
    db.query(AdminSession).filter(AdminSession.user_id == user.id).delete(
        synchronize_session=False
    )
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
    principal: AdminPrincipal = Depends(require_admin),
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
        if principal.role_key == "teacher":
            # 班主任只保留班级管理所需字段，不返回任何个体风险信号。
            brief.pop("risk_level", None)
            brief.pop("review_note", None)
            brief["review_status"] = "restricted"
            brief["risk_visibility"] = "restricted"
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
    _: None = Depends(require_counselor),
):
    row = db.get(Assessment, assessment_id)
    if not row or not row.report_json:
        raise HTTPException(status_code=404, detail="报告不存在或尚未生成")
    review = db.get(ReportReview, assessment_id)
    effective = _load_report(row)
    ai_report = effective
    if review and review.ai_report_json:
        try:
            ai_report = sign_report_media(json.loads(review.ai_report_json), row.id)
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
    principal: AdminPrincipal = Depends(require_counselor),
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
    review.reviewer_id = (principal.user.account if principal.user else "service")
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
    principal: AdminPrincipal = Depends(require_counselor),
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
    review.reviewer_id = (principal.user.account if principal.user else "service")

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
    principal: AdminPrincipal = Depends(require_admin),
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
    risk_visible = principal.role_key != "teacher"
    risk_distribution = [
        {"level": "L1", "label": "L1 平稳", "value": risk_counts["L1"]},
        {"level": "L2", "label": "L2 轻度关注", "value": risk_counts["L2"]},
        {"level": "L3", "label": "L3 中度关注", "value": risk_counts["L3"]},
        {"level": "L4", "label": "L4 重点关注", "value": risk_counts["L4"]},
    ] if risk_visible else []
    visible_high_risk = high_risk[:8] if risk_visible else []

    return _ok(
        request,
        {
            "summary": {
                "total_reports": len(rows),
                "pending_reviews": pending,
                "approved_reports": approved,
                "high_risk_reports": len(high_risk) if risk_visible else 0,
                "share_links": share_count,
                "total_items": total_items,
                "sample_sufficient": len(rows) >= 5,
                "risk_visibility": "full" if risk_visible else "restricted",
            },
            "risk_distribution": risk_distribution,
            "high_risk_students": visible_high_risk,
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
