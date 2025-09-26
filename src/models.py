from typing import Any

from pydantic import BaseModel, Field


class ActionRequest(BaseModel):
    action: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class ActionResult(BaseModel):
    status: bool
    output: str = ""
    error: str | None = None
