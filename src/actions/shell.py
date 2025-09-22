from fastapi import APIRouter
from pydantic import BaseModel
import subprocess
from ..models import ActionResult

router = APIRouter()


class ShellRequest(BaseModel):
    command: str


@router.post("/shell", response_model=ActionResult)
async def run_shell(req: ShellRequest):
    try:
        out = subprocess.check_output(
            req.command, shell=True, stderr=subprocess.STDOUT, text=True, timeout=10
        )
        return ActionResult(status="ok", output=out)
    except subprocess.CalledProcessError as e:
        return ActionResult(status="error", output=e.output)
    except Exception as e:
        return ActionResult(status="error", output=str(e))
