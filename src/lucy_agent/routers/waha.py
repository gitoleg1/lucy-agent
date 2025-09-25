from typing import Annotated, Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException
import httpx

from lucy_agent.clients.waha import WahaClient
from lucy_agent.security import require_api_key

router = APIRouter(prefix="/waha", tags=["waha"])


@router.get("/sessionInfo", dependencies=[Depends(require_api_key)])
def session_info() -> Dict[str, Any]:
    """מידע סשן מ-WAHA."""
    try:
        return WahaClient().session_info()
    except httpx.HTTPStatusError as err:
        raise HTTPException(
            status_code=err.response.status_code,
            detail=err.response.text,
        ) from err


@router.post("/sendText", dependencies=[Depends(require_api_key)])
def send_text(payload: Annotated[Dict[str, Any], Body(...)]) -> Dict[str, Any]:
    """
    שליחת טקסט.
    payload: חייב להכיל chatId/receiver ו-text/message.
    אופציונלי: quotedMsgId/quoted.
    """
    chat_id = payload.get("chatId") or payload.get("receiver")
    text = payload.get("text") or payload.get("message")
    quoted = payload.get("quotedMsgId") or payload.get("quoted")

    if not chat_id or not text:
        raise HTTPException(
            status_code=422,
            detail="Missing 'chatId'/'receiver' or 'text'/'message'.",
        )

    try:
        return WahaClient().send_text(chat_id=chat_id, text=text, quoted_msg_id=quoted)
    except httpx.HTTPStatusError as err:
        raise HTTPException(
            status_code=err.response.status_code,
            detail=err.response.text,
        ) from err
