# ruff: noqa: E501
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import shlex
import subprocess
import time
from typing import Any, Dict

from fastapi import APIRouter, Body, Request
from fastapi.responses import StreamingResponse

router = APIRouter()

# ===== Utilities (נשמור מה שהיה שימושי ב-SSE) =====

HEARTBEAT_INTERVAL = float(os.getenv("HEARTBEAT_INTERVAL_SECONDS", "1.0"))


def now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _sse(event: str, data: Dict[str, Any] | None) -> bytes:
    payload = "" if data is None else json.dumps(
        data, ensure_ascii=False, separators=(",", ":")
    )
    out = f"event: {event}\n"
    out += f"data: {payload}\n\n"
    return out.encode("utf-8")


# ===== SSE Demo (נשמר כדי לא לשבור /stream/tasks/{task_id}) =====

@router.get("/stream/tasks/{task_id}")
async def stream_task(task_id: str, request: Request):
    """
    זרם SSE דמה: started → heartbeat×3 → done
    """
    async def gen():
        # התחלה
        yield _sse(
            "started",
            {"task_id": task_id, "ts": now_iso(), "payload": {"status": "RUNNING"}},
        )
        # 3 פעימות לב
        for _ in range(3):
            await _sleep_or_disconnect(request, HEARTBEAT_INTERVAL)
            yield _sse(
                "heartbeat",
                {"task_id": task_id, "ts": now_iso(), "payload": {"ok": True}},
            )
        # סיום
        yield _sse(
            "done",
            {"task_id": task_id, "ts": now_iso(), "payload": {"status": "SUCCEEDED"}},
        )

    return StreamingResponse(gen(), media_type="text/event-stream")


async def _sleep_or_disconnect(request: Request, seconds: float) -> None:
    # שינה קצרה, יציאה אם הלקוח התנתק
    for _ in range(int(seconds * 10)):
        if await request.is_disconnected():
            return
        time.sleep(0.1)


# ======== MVP One-Shot: /quick-run ו-/agent/shell ========
# גרסה מינימלית לפרק 5: הרצת פקודה יחידה והחזרת מבנה אחיד.
# הערה: הקשחת API-Key ו-Rate-Limit יבואו בפרקים 6–7.

def _run_cmd(cmd: str, timeout_sec: int = 30) -> dict[str, Any]:
    """
    מריץ פקודה ב-Shell כאטום אחד ומחזיר dict קטן עם סטטוס/קוד/פלטים.
    """
    # נריץ כ: sh -lc "<cmd>" כדי לאפשר builtins/pipe וכו'
    shell = os.environ.get("SHELL") or "/bin/sh"
    full = f'{shell} -lc {shlex.quote(cmd)}'

    try:
        res = subprocess.run(  # nosec
            full,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
        exit_code = int(res.returncode)
        ok = exit_code == 0
        status = "SUCCEEDED" if ok else "FAILED"
        return {
            "status": status,
            "exit_code": exit_code,
            "stdout": (res.stdout or "")[:2000],
            "stderr": (res.stderr or "")[:2000],
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "FAILED",
            "exit_code": 124,
            "stdout": "",
            "stderr": f"timeout({timeout_sec}s)",
        }
    except Exception as e:
        return {
            "status": "FAILED",
            "exit_code": -1,
            "stdout": "",
            "stderr": f"{type(e).__name__}: {e}",
        }


@router.post("/quick-run")
def quick_run(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    MVP Quick-Run מינימלי: מצפה ל-{"cmd": "<shell>"} ומחזיר task/runs/audit.
    """
    cmd = str(payload.get("cmd") or "").strip()
    if not cmd:
        return {
            "task": {"status": "FAILED", "error": "missing 'cmd'"},
            "runs": [],
            "audit": {"events": []},
        }

    result = _run_cmd(cmd)
    task_status = result["status"]
    return {
        "task": {"status": task_status, "title": payload.get("title") or "quick-run"},
        "runs": [
            {
                "idx": 1,
                "type": "shell",
                "exit_code": result["exit_code"],
                "stdout_tail": result["stdout"],
                "stderr_tail": result["stderr"],
            }
        ],
        "audit": {"events": [{"type": "shell", "ts": now_iso(), "cmd": cmd}]},
    }


@router.post("/agent/shell")
def agent_shell(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    מעטפת דקה סביב quick-run לצורך בדיקות עישון של פרק 5.
    גוף הבקשה: {"cmd": "<shell>"}
    """
    cmd = str(payload.get("cmd") or "").strip()
    if not cmd:
        return {
            "status": "FAILED",
            "error": "missing 'cmd'",
            "result": {},
        }

    result = _run_cmd(cmd)
    # כדי להתאים לסקריפטי smoke שמצפים לשדה 'status' ברמה העליונה:
    return {
        "status": result["status"],
        "exit_code": result["exit_code"],
        "stdout": result["stdout"],
        "stderr": result["stderr"],
    }
