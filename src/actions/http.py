import json
from typing import Any

import httpx
from fastapi import APIRouter

from ..db import log_action
from ..models import ActionRequest, ActionResult

router = APIRouter()


@router.post("/http", response_model=ActionResult)
async def run_http(req: ActionRequest):
    """
    params:
      method: GET/POST/PUT/DELETE (ברירת מחדל: GET)
      url:    כתובת מלאה (חובה)
      headers: dict אופציונלי
      params:  dict לארגומנטים בשורת הכתובת (querystring)
      json:    dict לגוף JSON (אופציונלי)
      data:    dict/str לגוף טופס/טקסט (אופציונלי)
      timeout: שניות (ברירת מחדל: 10)
    """
    p: dict[str, Any] = req.params or {}
    method: str = (p.get("method") or "GET").upper()
    url: str = p.get("url") or ""
    headers: dict[str, str] | None = p.get("headers")
    qparams: dict[str, Any] | None = p.get("params")
    json_body: Any = p.get("json")
    data_body: Any = p.get("data")
    timeout: float = float(p.get("timeout") or 10)

    if not url:
        await log_action("http", json.dumps(p), "Missing URL", "error")
        return ActionResult(status="error", output="", error="Missing 'url' in params")

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.request(
                method,
                url,
                headers=headers,
                params=qparams,
                json=json_body,
                data=data_body,
            )
        out = f"HTTP {resp.status_code}\n{resp.text[:2000]}"
        status = "ok" if 200 <= resp.status_code < 400 else "error"
        await log_action("http", json.dumps(p), out, status)
        return ActionResult(status=status, output=out)
    except Exception as e:
        msg = f"HTTP ERROR: {type(e).__name__}: {e}"
        await log_action("http", json.dumps(p), msg, "error")
        return ActionResult(status="error", output="", error=msg)
