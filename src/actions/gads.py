from fastapi import APIRouter
from ..models import ActionRequest, ActionResult
from ..db import log_action

router = APIRouter()


@router.post("/gads", response_model=ActionResult)
async def run_gads(req: ActionRequest):
    # Placeholder בלבד – מימוש יבוא בהמשך
    await log_action("gads", str(req.params), "NOT_IMPLEMENTED", "error")
    return ActionResult(status="error", output="", error="Google Ads not implemented yet")
