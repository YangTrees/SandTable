from __future__ import annotations

import base64
import hmac
import io
import json
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import qrcode
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from .admin_api import (
    AdminPrincipal,
    ensure_admin_seed,
    require_admin,
    require_student,
    router as admin_router,
    workbench_router,
)
from .config import (
    APP_ENV,
    CORS_ORIGINS,
    ENABLE_API_DOCS,
    ENABLE_MANUAL,
    ENABLE_SERVICE_TOKEN,
    MEDIA_SIGNED_URL_TTL_SECONDS,
    MEDIA_SIGNING_SECRET,
    MEDIA_SIGNING_SECRET_CONFIGURED,
    MULTIMODAL_API_KEY,
    MULTIMODAL_MODEL,
    PUBLIC_BASE_URL,
    SEED_DEMO_USERS,
    SHARE_DEFAULT_EXPIRES_DAYS,
    UPLOAD_DIR,
)
from .db import SessionLocal, get_db, init_db
from .models import Assessment, ReportReview, ShareLink
from .report_engine import generate_report
from .schemas import AssessmentPayload, ShareRequest
from .utils import (
    iso_utc,
    media_signature,
    new_id,
    new_share_token,
    public_copy,
    sign_report_media,
    signed_media_url,
)

MAX_IMAGE_BYTES = 24 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 20_000_000
REPORT_VIEWER_PATH = Path(__file__).resolve().parents[2] / "report_viewer_v2.html"
ADMIN_DASHBOARD_PATH = Path(__file__).resolve().parents[2] / "admin_dashboard.html"
WORKBENCH_PATH = Path(__file__).resolve().parents[2] / "sandplay_workbench_react.html"
MANUAL_PATH = Path(__file__).resolve().parents[2] / "manual_web" / "心理沙盘系统_账户与全系统操作手册.html"
MANUAL_ASSETS_DIR = Path(__file__).resolve().parents[2] / "manual_web" / "assets"
ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets"

logger = logging.getLogger(__name__)


def _validate_release_config() -> None:
    if APP_ENV != "production":
        return
    release_errors: list[str] = []
    if not PUBLIC_BASE_URL.startswith("https://"):
        release_errors.append("PUBLIC_BASE_URL 必须为 https:// 公网域名")
    if "*" in CORS_ORIGINS:
        release_errors.append("CORS_ORIGINS 不能包含通配符 *")
    if not MEDIA_SIGNING_SECRET_CONFIGURED:
        release_errors.append("必须设置 MEDIA_SIGNING_SECRET（或 COUNSELOR_TOKEN）")
    if ENABLE_API_DOCS:
        release_errors.append("生产环境必须设置 ENABLE_API_DOCS=false")
    if ENABLE_MANUAL:
        release_errors.append("生产环境必须设置 ENABLE_MANUAL=false，避免内部手册和截图公网暴露")
    if SEED_DEMO_USERS:
        release_errors.append("生产环境必须设置 SEED_DEMO_USERS=false")
    if release_errors:
        raise RuntimeError("生产发布配置未通过：" + "；".join(release_errors))
    if ENABLE_SERVICE_TOKEN:
        logger.warning("生产环境已开启 ENABLE_SERVICE_TOKEN，请确认令牌仅用于受控运维")


@asynccontextmanager
async def lifespan(_: FastAPI):
    _validate_release_config()
    init_db()
    with SessionLocal() as db:
        ensure_admin_seed(db)
    yield


app = FastAPI(
    title="心理沙盘发展性评估 API",
    version="1.0",
    lifespan=lifespan,
    docs_url="/docs" if ENABLE_API_DOCS else None,
    redoc_url="/redoc" if ENABLE_API_DOCS else None,
    openapi_url="/openapi.json" if ENABLE_API_DOCS else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Counselor-Token", "X-Request-Id", "X-Share-Token"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "style-src 'self' 'unsafe-inline' https://miaoda.feishu.cn; "
        "font-src 'self' https://miaoda.feishu.cn https://sf3-scmcdn-cn.feishucdn.com; "
        "img-src 'self' data: blob:; "
        "connect-src 'self'; object-src 'none'; base-uri 'self'; "
        "frame-ancestors 'none'; form-action 'self'",
    )
    if request.url.scheme == "https":
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response


app.include_router(admin_router)
app.include_router(workbench_router)


@app.get("/media/{assessment_id}/{filename}")
async def protected_media(assessment_id: str, filename: str, exp: int = 0, sig: str = ""):
    """只提供短期签名 URL，避免公开静态目录被枚举或热链接。"""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", assessment_id or ""):
        raise HTTPException(status_code=404, detail="资源不存在")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+\.png", filename or ""):
        raise HTTPException(status_code=404, detail="资源不存在")
    if exp < int(time.time()):
        raise HTTPException(status_code=403, detail="图片链接已过期，请重新打开报告")
    if not hmac.compare_digest(sig, media_signature(assessment_id, filename, exp)):
        raise HTTPException(status_code=403, detail="图片链接签名无效")
    path = UPLOAD_DIR / assessment_id / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="资源不存在")
    return FileResponse(
        path,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"},
    )


if ENABLE_MANUAL and MANUAL_ASSETS_DIR.is_dir():
    app.mount("/manual/assets", StaticFiles(directory=MANUAL_ASSETS_DIR), name="manual-assets")
if ASSETS_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")


def _trace(request: Request) -> str:
    return request.headers.get("X-Request-Id") or f"req_{uuid.uuid4().hex[:20]}"


def ok(request: Request, data: Any, message: str = "success") -> dict[str, Any]:
    return {"code": "OK", "message": message, "data": data, "trace_id": _trace(request)}


def fail(request: Request, code: str, message: str, status_code: int, data: Any = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"code": code, "message": message, "data": data or {}, "trace_id": _trace(request)},
    )


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    errors = [{"field": ".".join(str(x) for x in item["loc"]), "reason": item["msg"]} for item in exc.errors()]
    return fail(request, "VALIDATION_INVALID_PAYLOAD", "请求数据不完整或格式不正确", 422, {"field_errors": errors})


@app.exception_handler(HTTPException)
async def http_handler(request: Request, exc: HTTPException):
    return fail(request, "HTTP_ERROR", str(exc.detail), exc.status_code)


def require_counselor(
    principal: AdminPrincipal = Depends(require_admin),
) -> AdminPrincipal:
    if principal.role_key not in {"counselor", "super_admin"}:
        raise HTTPException(status_code=403, detail="班主任账号不可查看个体心理报告")
    return principal


def _decode_base64(value: str | None) -> bytes | None:
    if not value:
        return None
    if value.startswith("data:"):
        value = value.split(",", 1)[-1]
    try:
        return base64.b64decode(value, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="图片数据格式不正确") from exc


def _normalise_uploaded_image(content: bytes, label: str = "图片") -> bytes:
    """只接受可正常解码的常见位图，并统一重编码为 PNG，避免伪造扩展名。"""
    if not content:
        raise HTTPException(status_code=422, detail=f"缺少{label}")
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format not in {"PNG", "JPEG", "WEBP"}:
                raise HTTPException(status_code=422, detail=f"{label}仅支持 PNG、JPEG 或 WebP")
            image.load()
            if image.width * image.height > 20_000_000:
                raise HTTPException(status_code=413, detail=f"{label}像素尺寸过大")
            buffer = io.BytesIO()
            image.convert("RGB").save(buffer, format="PNG", optimize=True)
            normalised = buffer.getvalue()
    except HTTPException:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"{label}无法识别或已损坏") from exc
    if len(normalised) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail=f"{label}重编码后超过 24MB")
    return normalised


async def _read_upload(upload: UploadFile | None, base64_value: str | None) -> bytes:
    if upload:
        content = await upload.read()
    else:
        content = _decode_base64(base64_value) or b""
    if not content:
        raise HTTPException(status_code=422, detail="缺少沙盘图片")
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="单张图片不得超过 24MB")
    return _normalise_uploaded_image(content, "沙盘图片")


async def _read_optional_upload(upload: UploadFile | None, base64_value: str | None) -> bytes | None:
    if upload:
        content = await upload.read()
    else:
        content = _decode_base64(base64_value)
    if not content:
        return None
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="单张图片不得超过 24MB")
    return _normalise_uploaded_image(content, "成绩单图片")


def _store_bytes(assessment_id: str, name: str, content: bytes) -> tuple[str, str]:
    directory = UPLOAD_DIR / assessment_id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(content)
    rel = f"{assessment_id}/{name}"
    return str(path), rel


def _clean_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """移除前端 data URI，并拒绝学生伪造教师观察或服务端内部字段。"""
    payload.pop("canvas_image_base64", None)
    payload["teacher_observation"] = ""
    for key in list(payload.keys()):
        if str(key).startswith("_"):
            payload.pop(key, None)
    for item in payload.get("items") or []:
        if isinstance(item, dict):
            item.pop("image", None)
    return payload


def _assessment_summary(row: Assessment) -> dict[str, Any]:
    return {
        "assessment_id": row.id,
        "status": row.status,
        "student_name": row.student_name,
        "student_no": row.student_no,
        "grade_level": row.grade_level,
        "gender": row.gender,
        "school_name": getattr(row, "school_name", ""),
        "class_name": getattr(row, "class_name", ""),
        "representative_item_id": row.representative_item_id,
        "representative_item_name": row.representative_item_name,
        "self_image": getattr(row, "self_image", "") or "",
        "self_image_note": getattr(row, "self_image_note", "") or "",
        "report_engine": row.report_engine,
        "created_at": iso_utc(row.created_at),
        "counselor_report_url": f"/api/v1/reports/{row.id}",
    }


def _clip_text(value: Any, limit: int = 260) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _normalise_academic_scores(value: Any) -> dict[str, Any]:
    """保留学生提交的结构化成绩；身份字段仍以学校账号为准。"""
    if not isinstance(value, dict):
        return {}
    scores: dict[str, Any] = {}
    for key in ("exam_name", "exam_date", "total_score", "class_rank"):
        text = _clip_text(value.get(key), 80)
        if text:
            scores[key] = text
    subjects = value.get("subjects")
    if isinstance(subjects, dict):
        cleaned_subjects: dict[str, str] = {}
        for subject, score in list(subjects.items())[:12]:
            name = _clip_text(subject, 24)
            text = _clip_text(score, 40)
            if name and text:
                cleaned_subjects[name] = text
        if cleaned_subjects:
            scores["subjects"] = cleaned_subjects
    return scores


def _student_report_brief(row: Assessment) -> dict[str, Any] | None:
    """学生端简略报告：只保留摘要、整体印象、六维方向、学业与建议。"""
    if not row.report_json:
        return None
    try:
        report = json.loads(row.report_json)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(report, dict):
        return None

    meta = report.get("meta") if isinstance(report.get("meta"), dict) else {}
    summary = report.get("summary_card") if isinstance(report.get("summary_card"), dict) else {}
    public = summary.get("public") if isinstance(summary.get("public"), dict) else {}
    if not public:
        public = summary
    chapter1 = report.get("chapter_1_overview") if isinstance(report.get("chapter_1_overview"), dict) else {}
    chapter3 = report.get("chapter_3_six_dimensions") if isinstance(report.get("chapter_3_six_dimensions"), dict) else {}
    chapter4 = report.get("chapter_4_academic") if isinstance(report.get("chapter_4_academic"), dict) else {}
    chapter9 = report.get("chapter_9_general_advice") if isinstance(report.get("chapter_9_general_advice"), dict) else {}

    signals = []
    for item in (public.get("signals") or [])[:4]:
        if isinstance(item, dict) and item.get("label"):
            signals.append({
                "label": _clip_text(item.get("label"), 40),
                "value": _clip_text(item.get("value"), 180),
                "tone": str(item.get("tone") or "neutral"),
            })

    scene_imagery = [
        _clip_text(item, 140)
        for item in (chapter1.get("scene_imagery") or [])[:4]
        if _clip_text(item, 140)
    ]
    scene_points = [
        _clip_text(chapter1.get(key), 160)
        for key in ("clusters", "blank_areas", "terrain_observation")
        if _clip_text(chapter1.get(key), 160)
    ]

    dimensions = []
    for item in (chapter3.get("dimensions") or [])[:6]:
        if isinstance(item, dict):
            dimensions.append({
                "name": _clip_text(item.get("name"), 40),
                "judgement": _clip_text(item.get("judgement"), 200),
                "confidence": _clip_text(item.get("confidence") or "中", 12),
            })

    subjects = []
    for item in (chapter4.get("subjects") or [])[:8]:
        if isinstance(item, dict):
            subjects.append({
                "subject": _clip_text(item.get("subject"), 20),
                "score": item.get("score"),
                "full_score": item.get("full_score"),
                "rate": item.get("rate"),
                "grade": _clip_text(item.get("grade"), 20),
            })
    total = chapter4.get("total") if isinstance(chapter4.get("total"), dict) else {}
    advice_items = [
        _clip_text(item, 160)
        for item in (chapter9.get("growth_mindset") or [])[:3]
        if _clip_text(item, 160)
    ]

    return {
        "report_no": _clip_text(meta.get("report_no"), 40),
        "generated_at": _clip_text(meta.get("generated_at"), 40),
        "headline": _clip_text(public.get("headline") or summary.get("headline"), 260),
        "signals": signals,
        "next_step": _clip_text(public.get("next_step") or summary.get("next_step"), 200),
        "note": _clip_text(public.get("note") or "本摘要为发展性评估参考，不含风险分级。", 200),
        "overall": {
            "title": _clip_text(chapter1.get("title"), 60),
            "scene_imagery": scene_imagery,
            "scene_points": scene_points,
        },
        "dimensions": dimensions,
        "academic": {
            "transcript_provided": bool(chapter4.get("transcript_provided")),
            "transcript_image_provided": bool(chapter4.get("transcript_image_url")),
            "overall_interpretation": _clip_text(chapter4.get("overall_interpretation"), 280),
            "subjects": subjects,
            "total": {
                "score": total.get("score"),
                "full_score": total.get("full_score"),
                "rate": total.get("rate"),
            },
            "strengths": _clip_text(chapter4.get("strengths"), 200),
            "weaknesses": _clip_text(chapter4.get("weaknesses"), 200),
            "trend": _clip_text(chapter4.get("trend"), 200),
        },
        "advice": advice_items,
        "disclaimer": _clip_text(chapter9.get("disclaimer") or meta.get("disclaimer"), 200),
    }


def _previous_assessment_context(db: Session, row: Assessment) -> dict[str, Any]:
    """同一学生上一份已完成报告的轻量摘要，不复制整份历史报告。"""
    student_no = str(row.student_no or "").strip()
    if not student_no:
        return {}
    previous = (
        db.query(Assessment)
        .filter(
            Assessment.student_no == student_no,
            Assessment.id != row.id,
            Assessment.report_json.isnot(None),
            Assessment.status == "completed",
            Assessment.created_at <= row.created_at,
        )
        .order_by(Assessment.created_at.desc())
        .first()
    )
    if not previous:
        return {}
    try:
        report = json.loads(previous.report_json or "{}")
    except json.JSONDecodeError:
        return {}
    chapter5 = report.get("chapter_5_risk") if isinstance(report.get("chapter_5_risk"), dict) else {}
    risk_dimensions = [
        {
            "key": str(item.get("key") or ""),
            "name": str(item.get("name") or ""),
            "level": str(item.get("level") or "L1").upper(),
            "label": str(item.get("label") or ""),
        }
        for item in (chapter5.get("dimensions") or [])
        if isinstance(item, dict)
    ]
    sample = ((report.get("meta") or {}).get("sample_quality") or {}) if isinstance(report.get("meta"), dict) else {}
    return {
        "assessment_id": previous.id,
        "report_no": str((report.get("meta") or {}).get("report_no") or f"PS-{previous.id[:8].upper()}"),
        "created_at": iso_utc(previous.created_at),
        "generated_at": str((report.get("meta") or {}).get("generated_at") or ""),
        "engine": str(previous.report_engine or ""),
        "lean_only": bool(sample.get("low_projection")),
        "representative_item_name": str(previous.representative_item_name or ""),
        "self_image": str(getattr(previous, "self_image", "") or ""),
        "risk_dimensions": risk_dimensions,
    }


@app.get("/api/v1/health")
async def health(request: Request):
    return ok(request, {"status": "ok", "time": iso_utc(datetime.utcnow())})


async def _generate_report_in_background(
    assessment_id: str,
    report_payload: dict[str, Any],
    sandplay_image: bytes,
    transcript_image: bytes | None,
    image_url: str,
    transcript_url: str | None,
) -> None:
    """学生提交后异步生成报告，避免提交请求阻塞在多模态模型上。"""
    try:
        report, engine = await generate_report(
            report_payload,
            sandplay_image=sandplay_image,
            transcript_image=transcript_image,
            image_url=image_url,
            transcript_url=transcript_url,
        )
    except Exception:
        logger.exception("后台生成测评报告失败 assessment_id=%s", assessment_id)
        with SessionLocal() as db:
            row = db.get(Assessment, assessment_id)
            if row is not None and row.status != "completed":
                row.status = "failed"
                db.commit()
        return

    with SessionLocal() as db:
        row = db.get(Assessment, assessment_id)
        if row is None:
            logger.warning("后台报告生成完成但测评记录不存在 assessment_id=%s", assessment_id)
            return
        if row.status == "completed":
            return
        row.report_json = json.dumps(report, ensure_ascii=False)
        row.report_engine = engine
        row.status = "completed"
        db.commit()


@app.post("/api/v1/assessments")
async def create_assessment(
    request: Request,
    background_tasks: BackgroundTasks,
    payload: str = Form(...),
    sandplay_image: UploadFile | None = File(default=None),
    sandplay_image_base64: str | None = Form(default=None),
    transcript_image: UploadFile | None = File(default=None),
    transcript_image_base64: str | None = Form(default=None),
    db: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_student),
):
    try:
        payload_obj = AssessmentPayload.model_validate(json.loads(payload))
    except json.JSONDecodeError:
        return fail(request, "VALIDATION_INVALID_PAYLOAD", "payload 不是合法 JSON", 422)
    except ValueError:
        return fail(request, "VALIDATION_INVALID_PAYLOAD", "payload 字段校验未通过", 422)

    if not payload_obj.consent:
        return fail(request, "CONSENT_REQUIRED", "请先确认知情同意，再提交沙盘作品", 422)

    raw_payload = _clean_payload(payload_obj.model_dump(mode="json"))
    item_ids = {str(item.get("id")) for item in raw_payload.get("items") or [] if isinstance(item, dict)}
    if payload_obj.representative_item_id not in item_ids:
        return fail(request, "VALIDATION_REPRESENTATIVE_NOT_FOUND", "代表沙具必须来自已放入沙盘的沙具", 422)

    # 测评身份以登录的学生账号为准，前端提交的姓名、学号、班级不可覆盖。
    student = principal.user
    if student is None:
        return fail(request, "FORBIDDEN", "学生账号信息缺失，请重新登录", 403)
    submitted_student = raw_payload.get("student") if isinstance(raw_payload.get("student"), dict) else {}
    academic_scores = _normalise_academic_scores(submitted_student.get("academic_scores"))
    bound_student = {
        "name": student.name or "学生",
        "student_no": student.student_no or student.account,
        "grade_level": student.grade_level or "未填写",
        "class_name": student.class_name or "",
        "school_name": student.department or "",
        "gender": submitted_student.get("gender") or "不透露",
        "seat_no": "",
        "contact_phone": "",
        "academic_scores": academic_scores,
    }
    raw_payload["student"] = bound_student

    sandplay_bytes = await _read_upload(sandplay_image, sandplay_image_base64)
    transcript_bytes = await _read_optional_upload(transcript_image, transcript_image_base64)

    assessment_id = new_id()
    sandplay_path, sandplay_rel = _store_bytes(assessment_id, "sandplay.png", sandplay_bytes)
    transcript_path = None
    transcript_rel = None
    if transcript_bytes:
        transcript_path, transcript_rel = _store_bytes(assessment_id, "transcript.png", transcript_bytes)

    row = Assessment(
        id=assessment_id,
        student_no=bound_student["student_no"],
        student_name=bound_student["name"],
        grade_level=bound_student["grade_level"],
        gender=bound_student["gender"],
        school_name=bound_student["school_name"],
        class_name=bound_student["class_name"],
        seat_no="",
        contact_phone="",
        academic_scores_json=json.dumps(academic_scores, ensure_ascii=False),
        representative_item_id=payload_obj.representative_item_id,
        representative_item_name=payload_obj.representative_item_name,
        self_image=str(payload_obj.self_image or "").strip(),
        self_image_note=str(payload_obj.self_image_note or "").strip() or None,
        sandplay_description=payload_obj.sandplay_description,
        self_narrative=payload_obj.self_narrative,
        consent=payload_obj.consent,
        sandplay_image_path=sandplay_path,
        transcript_image_path=transcript_path,
        input_payload=json.dumps(raw_payload, ensure_ascii=False),
        heightmap_json=json.dumps(raw_payload.get("heightmap") or {}, ensure_ascii=False),
        grid_distribution_json=json.dumps(raw_payload.get("grid_distribution") or {}, ensure_ascii=False),
        items_json=json.dumps(raw_payload.get("items") or [], ensure_ascii=False),
        status="analyzing",
    )
    db.add(row)
    db.commit()

    image_url = signed_media_url(PUBLIC_BASE_URL, assessment_id, "sandplay.png")
    transcript_url = signed_media_url(PUBLIC_BASE_URL, assessment_id, "transcript.png") if transcript_rel else None

    report_payload = dict(raw_payload)
    previous = _previous_assessment_context(db, row)
    if previous:
        report_payload["_previous_assessment"] = previous

    # 提交请求立即返回，报告生成放到响应之后的后台任务，避免学生长时间等待。
    background_tasks.add_task(
        _generate_report_in_background,
        assessment_id,
        report_payload,
        sandplay_bytes,
        transcript_bytes,
        image_url,
        transcript_url,
    )

    # 学生端只返回“已提交”回执，不返回临床报告正文。
    return ok(request, {
        "assessment_id": row.id,
        "status": row.status,
        "student_name": row.student_name,
        "student_no": row.student_no,
        "grade_level": row.grade_level,
        "class_name": row.class_name,
        "representative_item_name": row.representative_item_name,
        "created_at": iso_utc(row.created_at),
        "sandplay_image_url": image_url,
        "report_ready": False,
    }, message="作品已提交，报告正在后台生成")


@app.get("/api/v1/assessments/{assessment_id}/status")
async def get_student_assessment_status(
    request: Request,
    assessment_id: str,
    db: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_student),
):
    """学生查询本人提交的回执；报告完成后返回脱敏简略版。"""
    row = db.get(Assessment, assessment_id)
    if not row:
        return fail(request, "NOT_FOUND", "评估记录不存在", 404)

    student = principal.user
    student_no = (student.student_no or student.account or "").strip() if student else ""
    if not student or row.student_no != student_no or row.student_name != (student.name or "学生"):
        return fail(request, "FORBIDDEN", "无权查看该测评记录", 403)

    report_ready = row.status == "completed" and bool(row.report_json)
    payload = {
        "assessment_id": row.id,
        "status": row.status,
        "report_ready": report_ready,
        "created_at": iso_utc(row.created_at),
        "sandplay_image_url": signed_media_url(PUBLIC_BASE_URL, row.id, "sandplay.png") if row.sandplay_image_path else "",
    }
    if report_ready:
        payload["brief"] = _student_report_brief(row)
    return ok(request, payload)


@app.get("/api/v1/assessments/{assessment_id}")
async def get_assessment(
    request: Request,
    assessment_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_counselor),
):
    row = db.get(Assessment, assessment_id)
    if not row:
        return fail(request, "NOT_FOUND", "评估记录不存在", 404)
    report = json.loads(row.report_json) if row.report_json else None
    return ok(request, {**_assessment_summary(row), "report": sign_report_media(report, row.id) if report else report})



@app.post("/api/v1/reports/{assessment_id}/reanalyze")
async def reanalyze_report(
    request: Request,
    assessment_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_counselor),
):
    """用已配置的多模态模型重新分析既有记录，不允许静默退回模板报告。"""
    row = db.get(Assessment, assessment_id)
    if not row or not row.report_json:
        return fail(request, "NOT_FOUND", "报告不存在或尚未生成", 404)
    if not MULTIMODAL_API_KEY:
        return fail(
            request,
            "MODEL_NOT_CONFIGURED",
            "尚未配置多模态模型。请在 backend/.env 设置 MULTIMODAL_API_KEY、MULTIMODAL_BASE_URL、MULTIMODAL_MODEL 后重启后端。",
            409,
        )

    sandplay_path = Path(row.sandplay_image_path or "")
    if not sandplay_path.is_file():
        return fail(request, "IMAGE_NOT_FOUND", "原始沙盘图片已丢失，无法重新分析", 409)
    sandplay_bytes = sandplay_path.read_bytes()
    transcript_bytes = None
    transcript_url = None
    if row.transcript_image_path and Path(row.transcript_image_path).is_file():
        transcript_bytes = Path(row.transcript_image_path).read_bytes()
        transcript_url = signed_media_url(PUBLIC_BASE_URL, row.id, "transcript.png")


    try:
        payload = json.loads(row.input_payload or "{}")
    except json.JSONDecodeError:
        return fail(request, "PAYLOAD_INVALID", "原始测评数据损坏，无法重新分析", 422)

    previous = _previous_assessment_context(db, row)
    if previous:
        payload["_previous_assessment"] = previous
    try:
        report, engine = await generate_report(
            payload,
            sandplay_image=sandplay_bytes,
            transcript_image=transcript_bytes,
            image_url=signed_media_url(PUBLIC_BASE_URL, row.id, "sandplay.png"),
            transcript_url=transcript_url,
            allow_demo_fallback=False,
        )
    except Exception:
        logger.exception("重新生成报告失败 assessment_id=%s", assessment_id)
        return fail(request, "MODEL_CALL_FAILED", "多模态模型调用失败，请稍后重试", 502)

    if engine != "multimodal":
        return fail(request, "MODEL_CALL_FAILED", "模型未返回有效报告，已保留原报告未覆盖", 502)

    old_report = json.loads(row.report_json)
    old_meta = old_report.get("meta") or {}
    meta = report.setdefault("meta", {})
    if old_meta.get("report_no"):
        meta["report_no"] = old_meta["report_no"]
    meta["reanalyzed_at"] = iso_utc(datetime.utcnow())
    meta["reanalyze_source"] = "counselor"
    meta["engine"] = "multimodal"
    meta["engine_note"] = f"多模态模型生成（{MULTIMODAL_MODEL}），固定算法负责风险分级与质量门控"

    row.report_json = json.dumps(report, ensure_ascii=False)
    row.report_engine = engine
    row.report_revision = 0
    row.status = "completed"
    review = db.get(ReportReview, row.id)
    if review:
        review.status = "pending"
        review.ai_report_json = None
        review.draft_report_json = None
        review.draft_note = ""
        review.draft_updated_at = None
        review.review_applied_at = None
    db.commit()
    db.refresh(row)

    return ok(request, {
        "assessment_id": row.id,
        "report_no": meta.get("report_no"),
        "engine": engine,
        "model": MULTIMODAL_MODEL,
        "generation_usage": meta.get("generation_usage"),
        "report": sign_report_media(report, row.id),
    }, message="report reanalyzed by multimodal model")


@app.get("/api/v1/reports/{assessment_id}")
async def get_full_report(
    request: Request,
    assessment_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_counselor),
):
    row = db.get(Assessment, assessment_id)
    if not row or not row.report_json:
        return fail(request, "NOT_FOUND", "报告不存在或尚未生成", 404)
    return ok(request, {
        **_assessment_summary(row),
        "report": sign_report_media(json.loads(row.report_json), row.id),
    })


@app.post("/api/v1/reports/{assessment_id}/share")
async def create_share(
    request: Request,
    assessment_id: str,
    body: ShareRequest | None = None,
    db: Session = Depends(get_db),
    _: None = Depends(require_counselor),
):
    row = db.get(Assessment, assessment_id)
    if not row or not row.report_json:
        return fail(request, "NOT_FOUND", "报告不存在或尚未生成", 404)

    body = body or ShareRequest()
    active = db.query(ShareLink).filter(
        ShareLink.assessment_id == assessment_id,
        ShareLink.revoked.is_(False),
    ).order_by(ShareLink.created_at.desc()).first()
    if active and active.expires_at and active.expires_at < datetime.utcnow():
        active.revoked = True
        db.commit()
        active = None
    if body.regenerate or not active:
        token = new_share_token()
        days = body.expires_days if body.expires_days is not None else SHARE_DEFAULT_EXPIRES_DAYS
        active = ShareLink(
            token=token,
            assessment_id=assessment_id,
            expires_at=datetime.utcnow() + timedelta(days=days) if days else None,
        )
        db.add(active)
        db.commit()
        db.refresh(active)

    # 把分享令牌放在 fragment 中，避免进入反向代理访问日志、Referer 和浏览器历史。
    share_url = f"{PUBLIC_BASE_URL}/report-viewer#share_token={active.token}"
    api_url = f"{PUBLIC_BASE_URL}/api/v1/share/access"
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=8, border=2)
    qr.add_data(share_url)
    qr.make(fit=True)
    image = qr.make_image(fill_color="#24332d", back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    qr_data_uri = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")

    return ok(request, {
        "share_token": active.token,
        "share_url": share_url,
        "api_url": api_url,
        "qr_png_base64": qr_data_uri,
        "expires_at": iso_utc(active.expires_at),
        "long_term": active.expires_at is None,
        "visible_chapters": [
            "chapter_1_overview", "chapter_2_imagery", "chapter_3_six_dimensions",
            "chapter_4_academic", "chapter_6_interview", "chapter_7_career",
            "chapter_8_training_modules", "chapter_9_general_advice",
        ],
        "redacted": ["chapter_5_risk"],
    }, message="share link created")


def _get_share_or_error(request: Request, token: str, db: Session) -> tuple[ShareLink, Assessment]:
    link = db.get(ShareLink, token)
    if not link or link.revoked:
        raise HTTPException(status_code=404, detail="分享链接不存在或已撤回")
    if link.expires_at and link.expires_at < datetime.utcnow():
        raise HTTPException(status_code=410, detail="分享链接已过期")
    row = db.get(Assessment, link.assessment_id)
    if not row or not row.report_json:
        raise HTTPException(status_code=404, detail="报告不存在")
    link.access_count += 1
    link.last_accessed_at = datetime.utcnow()
    db.commit()
    return link, row


@app.get("/api/v1/share/access")
async def get_shared_report(
    request: Request,
    x_share_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    token = str(x_share_token or "").strip()
    if not token:
        return fail(request, "MISSING_SHARE_TOKEN", "缺少分享令牌", 401)
    link, row = _get_share_or_error(request, token, db)
    full = json.loads(row.report_json)
    return ok(request, {
        "share": {
            "token": link.token,
            "created_at": iso_utc(link.created_at),
            "expires_at": iso_utc(link.expires_at),
            "long_term": link.expires_at is None,
            "visibility": "student_guardian",
            "redacted_chapters": ["chapter_5_risk"],
        },
        "report": sign_report_media(public_copy(full), row.id),
    })


_HTML_NO_STORE = {"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"}


@app.get("/report-viewer")
async def report_viewer_page():
    if not REPORT_VIEWER_PATH.exists():
        raise HTTPException(status_code=404, detail="报告展示页尚未部署")
    return FileResponse(
        REPORT_VIEWER_PATH,
        media_type="text/html; charset=utf-8",
        headers=_HTML_NO_STORE,
    )


@app.get("/admin")
async def admin_page():
    if not ADMIN_DASHBOARD_PATH.exists():
        raise HTTPException(status_code=404, detail="管理后台页面尚未部署")
    return FileResponse(
        ADMIN_DASHBOARD_PATH,
        media_type="text/html; charset=utf-8",
        headers=_HTML_NO_STORE,
    )


@app.get("/manual")
async def manual_page_redirect():
    if not ENABLE_MANUAL:
        raise HTTPException(status_code=404, detail="页面不存在")
    return RedirectResponse(url="/manual/", status_code=307)


@app.get("/manual/")
async def manual_page():
    if not ENABLE_MANUAL:
        raise HTTPException(status_code=404, detail="页面不存在")
    if not MANUAL_PATH.exists():
        raise HTTPException(status_code=404, detail="操作手册页面尚未部署")
    return FileResponse(
        MANUAL_PATH,
        media_type="text/html; charset=utf-8",
        headers=_HTML_NO_STORE,
    )


@app.get("/workbench")
async def workbench_page():
    if not WORKBENCH_PATH.exists():
        raise HTTPException(status_code=404, detail="沙盘工作台页面尚未部署")
    return FileResponse(
        WORKBENCH_PATH,
        media_type="text/html; charset=utf-8",
        headers=_HTML_NO_STORE,
    )


@app.get("/share/{token}")
async def share_page(request: Request, token: str, db: Session = Depends(get_db)):
    link, _ = _get_share_or_error(request, token, db)
    return RedirectResponse(url=f"/report-viewer#share_token={link.token}", status_code=303)


@app.delete("/api/v1/shares/{token}")
async def revoke_share(
    request: Request,
    token: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_counselor),
):
    link = db.get(ShareLink, token)
    if not link:
        return fail(request, "NOT_FOUND", "分享链接不存在", 404)
    link.revoked = True
    db.commit()
    return ok(request, {"share_token": token, "revoked": True})


@app.get("/")
async def root():
    payload = {"service": "sandplay-assessment-api", "health": "/api/v1/health"}
    if ENABLE_API_DOCS:
        payload["docs"] = "/docs"
    return payload
