from __future__ import annotations

import asyncio
import datetime as dt
import json
import re
import time
from collections.abc import AsyncIterator
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter(prefix="/stream", tags=["stream"])

# === EventBus מינימלי לדוגמה (אפשר להחליף בבאסים הפנימי שלך) ===
_event_queues: Dict[str, asyncio.Queue[Dict[str, Any]]] = {}


def get_queue(task_id: str) -> asyncio.Queue[Dict[str, Any]]:
    q = _event_queues.get(task_id)
    if q is None:
        q = asyncio.Queue()
        _event_queues[task_id] = q
    return q


async def publish_update(task_id: str, payload: Dict[str, Any]) -> None:
    await get_queue(task_id).put({"type": "update", "data": payload, "ts": time.time()})


async def publish_done(task_id: str, payload: Dict[str, Any]) -> None:
    await get_queue(task_id).put({"type": "done", "data": payload, "ts": time.time()})


# === מודלים ===
class TaskEvent(BaseModel):
    type: str  # "heartbeat" | "update" | "done"
    data: Dict[str, Any] | str | None = None
    ts: float


# === עזרי זמן/פורמט ===
def now_iso() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def sse_event(event: str, data: Dict[str, Any] | None) -> bytes:
    payload = (
        ""
        if data is None
        else json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    )
    out = f"event: {event}\n"
    out += f"data: {payload}\n\n"
    return out.encode("utf-8")


# === נירמול נתונים שמגיעים מה-runner (גם אם הם repr של אובייקט) ===
_STATUS_TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED"}
_RE_STATUS = re.compile(
    r"status(?:=|:)\s*<[^>]*:\s*'([A-Z]+)'>|status(?:=|:)\s*'([A-Z]+)'", re.IGNORECASE
)


def normalize_update_payload(task_id: str, raw: Any) -> Dict[str, Any]:
    """
    מחזיר מילון JSON-תקני. אם raw הוא מחרוזת (repr),
    שומר ב-'raw' ומנסה לחלץ 'status'.
    """
    base: Dict[str, Any] = {"task_id": task_id, "ts": now_iso()}
    if isinstance(raw, dict):
        base["data"] = raw
        return base
    s = str(raw)
    status_match = _RE_STATUS.search(s)
    status = (status_match.group(1) or status_match.group(2)) if status_match else None
    base["data"] = {"raw": s}
    if status:
        base["data"]["status"] = status.upper()
    return base


def payload_is_terminal(data: Dict[str, Any]) -> bool:
    """
    מזהה סיום לפי data.status אם קיים (גם אם חולץ מ-repr).
    """
    status = None
    if isinstance(data, dict):
        inner = data.get("data") if "data" in data else data
        if isinstance(inner, dict):
            status = inner.get("status") or inner.get("Status") or inner.get("STATE")
    if isinstance(status, str):
        return status.upper() in _STATUS_TERMINAL
    return False


async def _event_stream(task_id: str) -> AsyncIterator[bytes]:
    queue = get_queue(task_id)
    heartbeat_interval = 15.0
    last_heartbeat = 0.0

    try:
        # heartbeat ראשון מיידי
        yield sse_event("heartbeat", {"task_id": task_id, "ts": now_iso()})
        last_heartbeat = time.time()

        while True:
            timeout = max(0.0, heartbeat_interval - (time.time() - last_heartbeat))
            try:
                evt = await asyncio.wait_for(queue.get(), timeout=timeout)
                evt_obj = TaskEvent(
                    type=evt["type"], data=evt.get("data"), ts=evt["ts"]
                )

                if evt_obj.type == "update":
                    norm = normalize_update_payload(task_id, evt_obj.data)
                    yield sse_event("update", norm)
                    if payload_is_terminal(norm):
                        yield sse_event(
                            "done",
                            {
                                "task_id": task_id,
                                "ts": now_iso(),
                                "data": norm.get("data", {}),
                            },
                        )
                        break

                elif evt_obj.type == "done":
                    norm = {
                        "task_id": task_id,
                        "ts": now_iso(),
                        "data": (
                            evt_obj.data
                            if isinstance(evt_obj.data, dict)
                            else {"raw": str(evt_obj.data)}
                        ),
                    }
                    yield sse_event("done", norm)
                    break

                else:
                    norm = {
                        "task_id": task_id,
                        "ts": now_iso(),
                        "data": {"raw": evt_obj.data, "note": "unknown_event_type"},
                    }
                    yield sse_event("update", norm)

            except TimeoutError:
                yield sse_event("heartbeat", {"task_id": task_id, "ts": now_iso()})
                last_heartbeat = time.time()
                continue

    except asyncio.CancelledError:
        return
    except Exception:
        return


@router.get("/tasks/{task_id}")
async def stream_task_events(request: Request, task_id: str):
    if not task_id:
        raise HTTPException(status_code=400, detail="task_id is required")

    async def generator():
        async for chunk in _event_stream(task_id):
            if await request.is_disconnected():
                break
            yield chunk

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
