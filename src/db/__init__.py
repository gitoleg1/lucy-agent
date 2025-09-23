# -*- coding: utf-8 -*-
"""
DB exports shim:
from src.db import get_session, safe_commit

- מנסה לייבא מימושים קיימים (session/core/database/db וכו').
- אם אין, מספק placeholder עם שגיאה ברורה כשהם נקראים.
"""
from importlib import import_module

__all__ = ["get_session", "safe_commit"]


def _import_first(candidates, names):
    for mod_name in candidates:
        try:
            m = import_module(mod_name)
        except Exception:
            continue
        ok = True
        got = []
        for n in names:
            if hasattr(m, n):
                got.append(getattr(m, n))
            else:
                ok = False
                break
        if ok:
            return got
    return None


_pair = _import_first(
    candidates=[
        "src.db.core",
        "src.db.session",
        "src.db.database",
        "src.database",
        "src.db",  # במקרה שמוגדרים כאן מלפני כן
    ],
    names=["get_session", "safe_commit"],
)

if _pair:
    get_session, safe_commit = _pair  # type: ignore
else:
    # Placeholders — כדי שהייבוא לא יכשל בשלב האימות; נקבל שגיאה ברורה אם יקראו בפועל.
    def get_session():
        raise RuntimeError(
            "get_session() לא נמצא במימוש הפרויקט. יש לספק מימוש אמיתי (למשל ב-src/db/session.py)"
        )

    def safe_commit(session):
        raise RuntimeError(
            "safe_commit() לא נמצא במימוש הפרויקט. יש לספק מימוש אמיתי (למשל ב-src/db/session.py)"
        )
