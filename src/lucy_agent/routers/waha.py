from __future__ import annotations

from typing import Annotated, Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException
import httpx

from lucy_agent.clients import WahaClient
from lucy_agent.security import require_api_key

router = APIRouter(prefix="/waha", tags=["waha"])


@router.get("/session", dependencies=[Depends(require_api_key)])
def session_info() -> Dict[str, Any]:
    """
    החזרת מידע סשן מ־Waha.
    """
    try:
        return WahaClient().session_info()
    except httpx.HTTPStatusError as e:
        # B904: יש להצמיד את החריגה המקורית בעזרת "from e"
        raise HTTPException(
            status_code=e.response.status_code, detail=e.response.text
        ) from e


@router.post("/sendText", dependencies=[Depends(require_api_key)])
def send_text(
    # B008: לא להשתמש בקריאה לפונקציה כברירת מחדל "Body(...)" בלי עטיפה
    payload: Annotated[Dict[str, Any], Body(...)]
) -> Dict[str, Any]:
    """
    שליחת טקסט דרך Waha.
    """
    chat_id = payload.get("chatId") or payload.get("receiver")
    text = payload.get("text") or payload.get("message")
    quoted = payload.get("quotedMsgId") or payload.get("quoted")

    try:
        return WahaClient().send_text(chat_id=chat_id, text=text, quoted_msg_id=quoted)
    except httpx.HTTPStatusError as e:
        # B904: להצמיד את החריגה המקורית
        raise HTTPException(
            status_code=e.response.status_code, detail=e.response.text
        ) from e
