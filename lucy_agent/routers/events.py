import os
import asyncio
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, status, Request
from fastapi.responses import StreamingResponse, JSONResponse, Response
from ..security import require_api_key

router = APIRouter()

HEARTBEAT_INTERVAL = float(os.getenv("HEARTBEAT_INTERVAL_SECONDS", "1.0"))
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
STARTED_AT = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
VERSION = "0.1.0"

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

def _sse_event(event: str | None, data: dict | str, *, event_id: int | None = None) -> bytes:
    """
    SSE תקין:
      id: <int>\n
      event: <name>\n
      data: <json/text>\n
      \n
    """
    payload = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    lines: list[str] = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    if event:
        lines.append(f"event: {event}")
    for ln in payload.splitlines() or [""]:
        lines.append(f"data: {ln}")
    lines.append("")
    return ("\n".join(lines) + "\n").encode("utf-8")

def _pick_cors_origin(request: Request) -> str | None:
    """
    בוחר Origin להחזרת Access-Control-Allow-Origin אם מותר.
    """
    origin = request.headers.get("origin")
    if not origin:
        return None
    if not ALLOWED_ORIGINS:
        return origin
    if origin in ALLOWED_ORIGINS:
        return origin
    return None

@router.get("/stream/tasks/{task_id}")
async def stream_task(task_id: str, request: Request, _: bool = Depends(require_api_key)):
    """
    זרם SSE: started → heartbeat×3 → done
    - 'retry: 3000' בתחילת הזרם.
    - כל אירוע כולל: id/ts/seq/task_id.
    - כותרות CORS ל-SSE לפי Origin.
    """
    async def gen():
        yield b"retry: 3000\n\n"

        eid = 1
        yield _sse_event(
            "started",
            {"event": "started", "ts": now_iso(), "task_id": task_id, "seq": 0, "status": "STARTED"},
            event_id=eid,
        )
        eid += 1

        for i in range(1, 4):
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            yield _sse_event(
                "heartbeat",
                {"event": "heartbeat", "ts": now_iso(), "task_id": task_id, "seq": i},
                event_id=eid,
            )
            eid += 1

        yield _sse_event(
            "done",
            {"event": "done", "ts": now_iso(), "task_id": task_id, "seq": 9999, "status": "SUCCEEDED"},
            event_id=eid,
        )

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }

    origin = _pick_cors_origin(request)
    if origin:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Vary"] = "Origin"

    return StreamingResponse(gen(), media_type="text/event-stream", headers=headers)

@router.get("/auth/check")
async def auth_check(_: bool = Depends(require_api_key)):
    """
    בדיקת מפתח: 204 אם תקין, 401/503 מטופלים ב-dependency.
    """
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.get("/health")
async def health():
    return JSONResponse({"status": "ok"}, status_code=status.HTTP_200_OK)

@router.get("/version")
async def version():
    return JSONResponse({"version": VERSION, "started_at": STARTED_AT}, status_code=status.HTTP_200_OK)
