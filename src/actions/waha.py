from fastapi import APIRouter

from ..db import log_action
from ..models import ActionRequest, ActionResult

router = APIRouter()


@router.post("/waha", response_model=ActionResult)
async def run_waha(req: ActionRequest):
    # Placeholder בלבד – מימוש יבוא בהמשך
    await log_action("waha", str(req.params), "NOT_IMPLEMENTED", "error")
    return ActionResult(status="error", output="", error="WAHA not implemented yet")
