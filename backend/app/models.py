from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    student_no: Mapped[str] = mapped_column(String(64), default="", index=True)
    student_name: Mapped[str] = mapped_column(String(80), default="匿名受测者")
    grade_level: Mapped[str] = mapped_column(String(40), default="未填写")
    gender: Mapped[str] = mapped_column(String(20), default="未填写")

    representative_item_id: Mapped[str] = mapped_column(String(120), default="")
    representative_item_name: Mapped[str] = mapped_column(String(120), default="")
    sandplay_description: Mapped[str] = mapped_column(Text, default="")
    self_narrative: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    consent: Mapped[bool] = mapped_column(Boolean, default=True)

    sandplay_image_path: Mapped[str] = mapped_column(Text, default="")
    transcript_image_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    input_payload: Mapped[str] = mapped_column(Text, default="{}")
    heightmap_json: Mapped[str] = mapped_column(Text, default="{}")
    grid_distribution_json: Mapped[str] = mapped_column(Text, default="{}")
    items_json: Mapped[str] = mapped_column(Text, default="[]")
    report_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    report_engine: Mapped[str] = mapped_column(String(40), default="demo")

    status: Mapped[str] = mapped_column(String(24), default="completed", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    shares: Mapped[list["ShareLink"]] = relationship(back_populates="assessment", cascade="all, delete-orphan")


class ShareLink(Base):
    __tablename__ = "share_links"

    token: Mapped[str] = mapped_column(String(96), primary_key=True)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    access_count: Mapped[int] = mapped_column(Integer, default=0)
    last_accessed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    assessment: Mapped[Assessment] = relationship(back_populates="shares")


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), default="")
    account: Mapped[str] = mapped_column(String(64), unique=True, index=True, default="")
    role_key: Mapped[str] = mapped_column(String(32), default="counselor", index=True)
    department: Mapped[str] = mapped_column(String(80), default="")
    grade_level: Mapped[str] = mapped_column(String(40), default="")
    class_name: Mapped[str] = mapped_column(String(40), default="")
    student_no: Mapped[str] = mapped_column(String(40), default="")
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ReportReview(Base):
    __tablename__ = "report_reviews"

    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    note: Mapped[str] = mapped_column(Text, default="")
    reviewer_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
