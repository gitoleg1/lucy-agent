from __future__ import annotations

import os
from typing import Any

import httpx


class WahaClient:
    def __init__(self) -> None:
        base = os.getenv("WAHA_BASE", "http://127.0.0.1:3000").rstrip("/")
        token = os.getenv("WAHA_TOKEN", "")
        self.session = os.getenv("WAHA_SESSION", "default")
        self.base = base

        hdrs: dict[str, str] = {}
        if token:
            hdrs["X-Token"] = token
        if self.session:
            hdrs["X-Session"] = self.session
        self.headers = hdrs

    def _url(self, path: str, with_session_query: bool = False) -> str:
        if with_session_query and self.session:
            sep = "&" if "?" in path else "?"
            return f"{self.base}{path}{sep}session={self.session}"
        return f"{self.base}{path}"

    def session_info(self) -> dict[str, Any]:
        with httpx.Client(timeout=10.0) as c:
            r = c.get(self._url(f"/api/sessions/{self.session}"), headers=self.headers)
            r.raise_for_status()
            return r.json()

    def send_text(
        self, chat_id: str, text: str, quoted_msg_id: str | None = None
    ) -> dict[str, Any]:
        """
        שולח טקסט ל-WAHA. קודם כל מנסה /api/sendText (עם/בלי ?session=),
        ורק אחר כך גרסאות נוספות. עוצר בהצלחה הראשונה; מחזיר JSON.
        אם כולן נכשלות — מעלה את השגיאה האחרונה (כולל קוד מ-WAHA).
        """
        payloads: list[dict[str, Any]] = []

        p1: dict[str, Any] = {"chatId": chat_id, "text": text}
        if quoted_msg_id:
            p1["quotedMessageId"] = quoted_msg_id
        payloads.append(p1)

        p2: dict[str, Any] = {"receiver": chat_id, "message": text}
        if quoted_msg_id:
            p2["quotedMsgId"] = quoted_msg_id
        payloads.append(p2)

        paths = [
            ("/api/sendText", True),
            ("/api/sendText", False),
            # גיבויים אפשריים—לא חובה אצלך, אבל נשאיר למקרה ותחליף מנוע
            ("/api/v1/sendText", True),
            ("/api/v1/sendText", False),
            ("/sendText", True),
            ("/sendText", False),
        ]

        last_exc: Exception | None = None
        with httpx.Client(timeout=15.0) as c:
            for path, put_session in paths:
                url = self._url(path, with_session_query=put_session)
                for payload in payloads:
                    try:
                        r = c.post(url, headers=self.headers, json=payload)
                        if r.status_code in (404, 405):
                            # לא הנתיב הזה—נמשיך לנסות אחרים
                            last_exc = httpx.HTTPStatusError(
                                "not found/method", request=r.request, response=r
                            )
                            continue
                        r.raise_for_status()
                        return r.json()
                    except httpx.HTTPStatusError as e:
                        # נזכור שגיאת סטטוס כדי שתחזור החוצה (עם קוד WAHA)
                        last_exc = e
                        continue
                    except Exception as e:
                        last_exc = e
                        continue

        if last_exc:
            raise last_exc
        raise RuntimeError("WAHA send_text: all variants failed")
