from typing import Any, Optional

from pydantic import BaseModel, Field


class ActionRequest(BaseModel):
    action: Optional[str] = None
    params: dict[str, Any] = Field(default_factory=dict)


class ActionResult(BaseModel):
    status: bool
    output: str = ""
    error: Optional[str] = None
