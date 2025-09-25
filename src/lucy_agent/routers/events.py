from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from starlette.responses import StreamingResponse

from ..security import require_api_key

router = APIRouter(
    prefix="/stream",
    tags=["stream"],
    dependencies=[Depends(require_api_key)],
)


def _sse(event: str | None, data: dict) -> bytes:
    """מייצר אירוע SSE תקין"""
    payload = json.dumps(data, ensure_ascii=False)
    lines = []
    if event:
        lines.append(f"event: {event}")
    for line in payload.splitlines():
        lines.append(f"data: {line}")
    lines.append("")  # שורה ריקה בין אירועים
    return ("\n".join(lines) + "\n").encode("utf-8")


async def _gen(task_id: str) -> AsyncIterator[bytes]:
    # התחלה
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    yield _sse(
        "started", {"task_id": task_id, "ts": now, "payload": {"status": "RUNNING"}}
    )
    # 3 פעימות לב
    for _ in range(3):
        await asyncio.sleep(1)
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        yield _sse("heartbeat", {"task_id": task_id, "ts": now})
    # סיום
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    yield _sse(
        "done", {"task_id": task_id, "ts": now, "payload": {"status": "SUCCEEDED"}}
    )


@router.get(
    "/tasks/{task_id}",
    summary="SSE Task Events",
    description="SSE endpoint: /stream/tasks/{task_id}",
)
async def sse_task_events(task_id: str):
    return StreamingResponse(
        _gen(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
