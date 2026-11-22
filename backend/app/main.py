from __future__ import annotations

import base64
import io
import json
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import qrcode
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .admin_api import ensure_admin_seed, router as admin_router
from .config import (
    COUNSELOR_TOKEN,
    CORS_ORIGINS,
    MULTIMODAL_API_KEY,
    MULTIMODAL_MODEL,
    PUBLIC_BASE_URL,
    UPLOAD_DIR,
)
from .db import SessionLocal, get_db, init_db
from .models import Assessment, ReportReview, ShareLink
from .report_engine import generate_report
from .schemas import AssessmentPayload, ShareRequest
from .utils import iso_utc, new_id, new_share_token, public_copy

MAX_IMAGE_BYTES = 24 * 1024 * 1024
REPORT_VIEWER_PATH = Path(__file__).resolve().parents[2] / "report_viewer_v2.html"
ADMIN_DASHBOARD_PATH = Path(__file__).resolve().parents[2] / "admin_dashboard.html"
WORKBENCH_PATH = Path(__file__).resolve().parents[2] / "sandplay_workbench_react.html"
ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    with SessionLocal() as db:
        ensure_admin_seed(db)
    yield


app = FastAPI(title="心理沙盘发展性评估 API", version="1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(admin_router)
app.mount("/media", StaticFiles(directory=UPLOAD_DIR), name="media")
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
    x_counselor_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> None:
    token = x_counselor_token or ""
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token or token != COUNSELOR_TOKEN:
        raise HTTPException(status_code=401, detail="咨询师后台令牌无效")


def _decode_base64(value: str | None) -> bytes | None:
    if not value:
        return None
    if value.startswith("data:"):
        value = value.split(",", 1)[-1]
    try:
        return base64.b64decode(value)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"base64 图片解码失败: {exc}") from exc


async def _read_upload(upload: UploadFile | None, base64_value: str | None) -> bytes:
    if upload:
        content = await upload.read()
    else:
        content = _decode_base64(base64_value) or b""
    if not content:
        raise HTTPException(status_code=422, detail="缺少沙盘图片")
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="单张图片不得超过 24MB")
    return content


async def _read_optional_upload(upload: UploadFile | None, base64_value: str | None) -> bytes | None:
    if upload:
        content = await upload.read()
    else:
        content = _decode_base64(base64_value)
    if content and len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="单张图片不得超过 24MB")
    return content or None


def _store_bytes(assessment_id: str, name: str, content: bytes) -> tuple[str, str]:
    directory = UPLOAD_DIR / assessment_id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(content)
    rel = f"{assessment_id}/{name}"
    return str(path), rel


def _clean_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """移除前端 data URI，避免数据库重复存储大字段。"""
    payload.pop("canvas_image_base64", None)
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
        "report_engine": row.report_engine,
        "created_at": iso_utc(row.created_at),
        "counselor_report_url": f"/api/v1/reports/{row.id}",
    }


@app.get("/api/v1/health")
async def health(request: Request):
    return ok(request, {"status": "ok", "time": iso_utc(datetime.utcnow())})


@app.post("/api/v1/assessments")
async def create_assessment(
    request: Request,
    payload: str = Form(...),
    sandplay_image: UploadFile | None = File(default=None),
    sandplay_image_base64: str | None = Form(default=None),
    transcript_image: UploadFile | None = File(default=None),
    transcript_image_base64: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    try:
        payload_obj = AssessmentPayload.model_validate(json.loads(payload))
    except (json.JSONDecodeError, ValueError) as exc:
        return fail(request, "VALIDATION_INVALID_PAYLOAD", f"payload JSON 解析或校验失败: {exc}", 422)

    raw_payload = _clean_payload(payload_obj.model_dump(mode="json"))
    item_ids = {str(item.get("id")) for item in raw_payload.get("items") or [] if isinstance(item, dict)}
    if payload_obj.representative_item_id not in item_ids:
        return fail(request, "VALIDATION_REPRESENTATIVE_NOT_FOUND", "代表沙具必须来自已放入沙盘的沙具", 422)

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
        student_no=payload_obj.student.student_no,
        student_name=payload_obj.student.name or "匿名受测者",
        grade_level=payload_obj.student.grade_level or "未填写",
        gender=payload_obj.student.gender or "未填写",
        school_name=payload_obj.student.school_name,
        class_name=payload_obj.student.class_name,
        seat_no=payload_obj.student.seat_no,
        contact_phone=payload_obj.student.contact_phone,
        academic_scores_json=json.dumps(payload_obj.student.academic_scores or {}, ensure_ascii=False),
        representative_item_id=payload_obj.representative_item_id,
        representative_item_name=payload_obj.representative_item_name,
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

    image_url = f"{PUBLIC_BASE_URL}/media/{sandplay_rel}"
    transcript_url = f"{PUBLIC_BASE_URL}/media/{transcript_rel}" if transcript_rel else None
    try:
        report, engine = await generate_report(
            raw_payload,
            sandplay_image=sandplay_bytes,
            transcript_image=transcript_bytes,
            image_url=image_url,
            transcript_url=transcript_url,
        )
    except Exception as exc:
        row.status = "failed"
        db.commit()
        return fail(request, "REPORT_GENERATION_FAILED", f"报告生成失败: {type(exc).__name__}: {exc}", 502)

    row.report_json = json.dumps(report, ensure_ascii=False)
    row.report_engine = engine
    row.status = "completed"
    db.commit()
    db.refresh(row)

    return ok(request, {
        **_assessment_summary(row),
        "report": report,
        "sandplay_image_url": image_url,
        "transcript_image_url": transcript_url,
        "counselor_access": {"header": "X-Counselor-Token"},
        "share_hint": f"POST /api/v1/reports/{row.id}/share",
    }, message="assessment completed")


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
    return ok(request, {**_assessment_summary(row), "report": report})


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
        transcript_url = f"{PUBLIC_BASE_URL}/media/{row.id}/transcript.png"

    try:
        payload = json.loads(row.input_payload or "{}")
    except json.JSONDecodeError:
        return fail(request, "PAYLOAD_INVALID", "原始测评数据损坏，无法重新分析", 422)

    try:
        report, engine = await generate_report(
            payload,
            sandplay_image=sandplay_bytes,
            transcript_image=transcript_bytes,
            image_url=f"{PUBLIC_BASE_URL}/media/{row.id}/sandplay.png",
            transcript_url=transcript_url,
            allow_demo_fallback=False,
        )
    except Exception as exc:
        return fail(request, "MODEL_CALL_FAILED", f"多模态模型调用失败：{type(exc).__name__}: {exc}", 502)

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
        "report": report,
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
        "report": json.loads(row.report_json),
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
        active = ShareLink(
            token=token,
            assessment_id=assessment_id,
            expires_at=datetime.utcnow() + timedelta(days=body.expires_days) if body.expires_days else None,
        )
        db.add(active)
        db.commit()
        db.refresh(active)

    share_url = f"{PUBLIC_BASE_URL}/share/{active.token}"
    api_url = f"{PUBLIC_BASE_URL}/api/v1/share/{active.token}"
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


@app.get("/api/v1/share/{token}")
async def get_shared_report(request: Request, token: str, db: Session = Depends(get_db)):
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
        "report": public_copy(full),
    })


@app.get("/report-viewer")
async def report_viewer_page():
    if not REPORT_VIEWER_PATH.exists():
        raise HTTPException(status_code=404, detail="报告展示页尚未部署")
    return FileResponse(REPORT_VIEWER_PATH, media_type="text/html; charset=utf-8")


@app.get("/admin")
async def admin_page():
    if not ADMIN_DASHBOARD_PATH.exists():
        raise HTTPException(status_code=404, detail="管理后台页面尚未部署")
    return FileResponse(ADMIN_DASHBOARD_PATH, media_type="text/html; charset=utf-8")


@app.get("/workbench")
async def workbench_page():
    if not WORKBENCH_PATH.exists():
        raise HTTPException(status_code=404, detail="沙盘工作台页面尚未部署")
    return FileResponse(WORKBENCH_PATH, media_type="text/html; charset=utf-8")


@app.get("/share/{token}")
async def share_page(request: Request, token: str, db: Session = Depends(get_db)):
    link, _ = _get_share_or_error(request, token, db)
    return RedirectResponse(url=f"/report-viewer?share_token={link.token}", status_code=303)


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
    return {"service": "sandplay-assessment-api", "docs": "/docs", "health": "/api/v1/health"}
