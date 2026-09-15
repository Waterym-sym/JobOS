from typing import Any

from pydantic import BaseModel, Field


class ErrorEnvelope(BaseModel):
    code: str
    message: str
    trace_id: str
    details: dict[str, Any] = Field(default_factory=dict)
