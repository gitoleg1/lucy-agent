from fastapi import APIRouter
from ..models import ActionRequest, ActionResult
from ..db import log_action

router = APIRouter()

@router.post("/waha", response_model=ActionResult)
async def run_waha(req: ActionRequest):
    # Placeholder בלבד – מימוש יבוא בהמשך
    await log_action("waha", str(req.params), "NOT_IMPLEMENTED", "error")
    return ActionResult(status="error", output="", error="WAHA not implemented yet")
