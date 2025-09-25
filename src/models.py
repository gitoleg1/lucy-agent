from typing import Any, Dict

from pydantic import BaseModel, Field


class ActionRequest(BaseModel):
    action: str | None = None
    params: Dict[str, Any] = Field(default_factory=dict)


class ActionResult(BaseModel):
    status: bool
    output: str = ""
    error: str | None = None
