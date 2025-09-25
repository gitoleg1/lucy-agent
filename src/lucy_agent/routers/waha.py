from __future__ import annotations

from typing import Any, Dict

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException

from ..clients.waha_client import WahaClient
from ..security import require_api_key

router = APIRouter(prefix="/waha", tags=["waha"])


@router.get("/session", dependencies=[Depends(require_api_key)])
def get_session_info() -> Dict[str, Any]:
    try:
        return WahaClient().session_info()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


@router.post("/sendText", dependencies=[Depends(require_api_key)])
def send_text(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    chat_id = payload.get("chatId") or payload.get("receiver")
    text = payload.get("text") or payload.get("message")
    quoted = payload.get("quotedMessageId") or payload.get("quotedMsgId")
    if not chat_id or not text:
        raise HTTPException(
            status_code=400, detail="chatId/text (or receiver/message) are required"
        )
    try:
        return WahaClient().send_text(chat_id=chat_id, text=text, quoted_msg_id=quoted)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
