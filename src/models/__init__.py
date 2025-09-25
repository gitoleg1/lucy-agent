"""
Aggregator exports for ORM models so that:
from src.models import Task, Run, Action, AuditLog
will work regardless of the file layout.

We try common module names and fall back gracefully.
"""

from importlib import import_module

__all__ = ["Task", "Run", "Action", "AuditLog"]


def _try(paths):
    for mod_name, attr in paths:
        try:
            m = import_module(mod_name)
            obj = getattr(m, attr, None)
            if obj is not None:
                return obj
        except Exception:
            continue
    return None


# ניסיונות שכיחים לשמות קבצים/מודולים
Task = _try(
    [
        ("src.models.task", "Task"),
        ("src.models.tasks", "Task"),
        ("src.models.models", "Task"),
        ("src.models.entities", "Task"),
    ]
)
Run = _try(
    [
        ("src.models.run", "Run"),
        ("src.models.runs", "Run"),
        ("src.models.models", "Run"),
        ("src.models.entities", "Run"),
    ]
)
Action = _try(
    [
        ("src.models.action", "Action"),
        ("src.models.actions", "Action"),
        ("src.models.models", "Action"),
        ("src.models.entities", "Action"),
    ]
)
AuditLog = _try(
    [
        ("src.models.audit", "AuditLog"),
        ("src.models.audit_log", "AuditLog"),
        ("src.models.models", "AuditLog"),
        ("src.models.entities", "AuditLog"),
    ]
)

# השארת סמלים גם אם לא נמצאו (ייבוא לא יקרוס; שימוש יקבל AttributeError ברור)
if Task is None:
    Task = None  # type: ignore
if Run is None:
    Run = None  # type: ignore
if Action is None:
    Action = None  # type: ignore
if AuditLog is None:
    AuditLog = None  # type: ignore
