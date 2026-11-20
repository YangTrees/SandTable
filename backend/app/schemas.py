from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StudentInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    student_no: str = ""
    name: str = "匿名受测者"
    grade_level: str = "未填写"
    gender: str = "未填写"


class HeightMap(BaseModel):
    model_config = ConfigDict(extra="allow")

    width: float = 1200
    depth: float = 760
    cols: int = Field(default=161, ge=2)
    rows: int = Field(default=101, ge=2)
    values: list[float] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)

    @field_validator("values")
    @classmethod
    def check_values(cls, values: list[float]) -> list[float]:
        if values and len(values) > 40000:
            raise ValueError("heightmap.values 过大，最多 40000 个采样点")
        return values


class AssessmentPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: str = "1.0"
    student: StudentInfo = Field(default_factory=StudentInfo)
    items: list[dict[str, Any]] = Field(default_factory=list)
    grid_distribution: dict[str, Any] = Field(default_factory=dict)
    heightmap: HeightMap = Field(default_factory=HeightMap)
    representative_item_id: str = Field(min_length=1)
    representative_item_name: str = ""
    sandplay_description: str = Field(min_length=1, max_length=4000)
    self_narrative: str | None = Field(default=None, max_length=6000)
    teacher_observation: str | None = Field(default=None, max_length=4000)
    consent: bool = True

    @field_validator("representative_item_id")
    @classmethod
    def representative_must_exist(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("必须选择最能代表自己的沙具")
        return value.strip()


class ShareRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    expires_days: int | None = Field(default=None, ge=1, le=3650)
    regenerate: bool = False


class ReportEnvelope(BaseModel):
    """九章节报告的最小结构契约。具体内容允许扩展，但章节不可缺失或改名。"""

    model_config = ConfigDict(extra="allow")

    schema_version: Literal["1.0"] = "1.0"
    template: str
    meta: dict[str, Any]
    chapter_1_overview: dict[str, Any]
    chapter_2_imagery: dict[str, Any]
    chapter_3_six_dimensions: dict[str, Any]
    chapter_4_academic: dict[str, Any]
    chapter_5_risk: dict[str, Any]
    chapter_6_interview: dict[str, Any]
    chapter_7_career: dict[str, Any]
    chapter_8_training_modules: dict[str, Any]
    chapter_9_general_advice: dict[str, Any]

    @field_validator("chapter_5_risk")
    @classmethod
    def risk_is_counselor_only(cls, value: dict[str, Any]) -> dict[str, Any]:
        if value.get("visibility") not in {None, "counselor_only"}:
            raise ValueError("chapter_5_risk.visibility 必须是 counselor_only")
        return value
