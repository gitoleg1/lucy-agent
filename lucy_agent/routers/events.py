# ruff: noqa: E501
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import shlex
import subprocess
import time
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from lucy_agent.security import require_api_key

router = APIRouter()

HEARTBEAT_INTERVAL = float(os.getenv("HEARTBEAT_INTERVAL_SECONDS", "1.0"))
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
STARTED_AT = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
VERSION = "0.1.0"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sse(event: str | None, data: dict | str) -> bytes:
    payload = "" if data is None else json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    out = f"event: {event}\n"
    out += f"data: {payload}\n\n"
    return out.encode("utf-8")


async def _sleep_or_disconnect(request: Request, seconds: float) -> None:
    steps = max(1, int(seconds * 10))
    for _ in range(steps):
        if await request.is_disconnected():
            return
        time.sleep(0.1)


@router.get("/stream/tasks/{task_id}")
async def stream_task(task_id: str, request: Request, _: bool = Depends(require_api_key)):
    """זרם SSE דמו: started → heartbeat×3 → done"""
    async def gen():
        yield _sse("started", {"task_id": task_id, "ts": now_iso(), "payload": {"status": "RUNNING"}})
        for _ in range(3):
            await _sleep_or_disconnect(request, HEARTBEAT_INTERVAL)
            yield _sse("heartbeat", {"task_id": task_id, "ts": now_iso(), "payload": {"ok": True}})
        yield _sse("done", {"task_id": task_id, "ts": now_iso(), "payload": {"status": "SUCCEEDED"}})
    return StreamingResponse(gen(), media_type="text/event-stream")


def _run_cmd(cmd: str, timeout_sec: int = 30) -> Dict[str, Any]:
    """מריץ פקודה אחת ב־shell ומחזיר סטטוס/קוד/פלטים (חיתוך ל־2000 תווים)."""
    shell = os.environ.get("SHELL") or "/bin/sh"
    full = f"{shell} -lc {shlex.quote(cmd)}"
    try:
        res = subprocess.run(full, shell=True, capture_output=True, text=True, timeout=timeout_sec)  # nosec
        exit_code = int(res.returncode)
        status_str = "SUCCEEDED" if exit_code == 0 else "FAILED"
        return {
            "status": status_str,
            "exit_code": exit_code,
            "stdout": (res.stdout or "")[:2000],
            "stderr": (res.stderr or "")[:2000],
        }
    except subprocess.TimeoutExpired:
        return {"status": "FAILED", "exit_code": 124, "stdout": "", "stderr": f"timeout({timeout_sec}s)"}
    except Exception as e:
        return {"status": "FAILED", "exit_code": -1, "stdout": "", "stderr": f"{type(e).__name__}: {e}"}


@router.post("/quick-run")
def quick_run(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:  # noqa: B008
    """
    MVP Quick-Run: קלט {"cmd": "<shell>"} → פלט task/runs/audit.
    """
    cmd = str(payload.get("cmd") or "").strip()
    if not cmd:
        return {"task": {"status": "FAILED", "error": "missing 'cmd'"}, "runs": [], "audit": {"events": []}}
    result = _run_cmd(cmd)
    return {
        "task": {"status": result["status"], "title": payload.get("title") or "quick-run"},
        "runs": [{"idx": 1, "type": "shell", "exit_code": result["exit_code"],
                  "stdout_tail": result["stdout"], "stderr_tail": result["stderr"]}],
        "audit": {"events": [{"type": "shell", "ts": now_iso(), "cmd": cmd}]},
    }


@router.post("/agent/shell")
def agent_shell(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:  # noqa: B008
    """מעטפת דקה סביב quick-run: גוף {"cmd":"..."}; פלט status/exit_code/stdout/stderr."""
    cmd = str(payload.get("cmd") or "").strip()
    if not cmd:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing 'cmd'")
    return _run_cmd(cmd)
