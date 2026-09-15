"""Pydantic models for extension -> server events and command receipts.

Shapes mirror the frozen contracts/ws schemas. Contract tests reject drift;
these runtime models are an implementation of that machine-readable truth.
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ------------------------------------------------------------------ raw-job


class BossJson(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    title: str | None = None
    is_headhunter: bool | None = None
    is_friend: bool | None = None
    has_interview: bool | None = None
    is_gold_interviewer: bool | None = None


SalaryUnit = Literal["month_K", "month_yuan", "day", "hour", "year", "unknown"]


class RawJobPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["boss"]
    ext_id: str = Field(min_length=1)
    tier: Literal["list", "detail"]
    batch_id: UUID | None = None
    fingerprint: str | None = None
    list_url: str | None = None
    title: str | None = None
    company: str | None = None
    city: str | None = None
    salary_text: str | None = None
    low_salary: float | None = None
    high_salary: float | None = None
    salary_unit: SalaryUnit = "unknown"
    exp_text: str | None = None
    degree: str | None = None
    list_tags: list[str] = Field(default_factory=list)
    boss_name: str | None = None
    jd_text: str | None = None
    skill_tags: list[str] = Field(default_factory=list)
    industry: str | None = None
    stage: str | None = None
    scale: str | None = None
    address: str | None = None
    company_desc: str | None = None
    active_time: str | None = None
    active_at: datetime | None = None
    ats_direct_post: bool | None = None
    boss_json: BossJson = Field(default_factory=BossJson)
    list_json: dict[str, Any] | None = None
    detail_json: dict[str, Any] | None = None
    captured_at: datetime | None = None

    @model_validator(mode="after")
    def require_list_identity(self) -> "RawJobPayload":
        if self.tier == "list" and (not self.title or not self.company):
            raise ValueError("title and company are required when tier=list")
        return self


# ------------------------------------------------------------------ events


class CapturePhasePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phase: Literal["list", "detail"]
    done: int = Field(ge=0)
    total: int = Field(ge=0)
    current: str = Field(min_length=1)


class CaptureStats(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: int = Field(ge=0)
    dup: int = Field(ge=0)
    risk_halted: bool = False


class CaptureCompletedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capture_id: UUID
    stats: CaptureStats
    finished_at: datetime


class CaptureErrorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    recoverable: bool
    risk: bool


class EventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    v: Literal[1]
    kind: Literal["event"]
    id: UUID
    type: str = Field(min_length=1)
    capture_id: UUID | None = None
    command_id: UUID | None = None
    ts: datetime | None = None
    payload: dict[str, Any]


EVENT_PAYLOAD_MODELS: dict[str, type[BaseModel]] = {
    "capture.phase": CapturePhasePayload,
    "job.captured": RawJobPayload,
    "job.updated": RawJobPayload,
    "capture.completed": CaptureCompletedPayload,
    "capture.error": CaptureErrorPayload,
}

# ---------------------------------------------------------------- receipts


class ReceiptEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    v: Literal[1]
    kind: Literal["receipt"]
    id: UUID
    type: Literal[
        "command.started",
        "command.progress",
        "command.completed",
        "command.error",
    ]
    capture_id: UUID | None = None
    command_id: UUID | None = None
    ts: datetime | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
