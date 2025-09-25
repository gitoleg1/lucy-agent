from fastapi import APIRouter

from ..models import ActionResult, EchoRequest

router = APIRouter()


@router.post("/echo", response_model=ActionResult)
async def echo(req: EchoRequest):
    return ActionResult(status="ok", output=req.text)
