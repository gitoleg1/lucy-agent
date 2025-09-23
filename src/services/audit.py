import json
from uuid import uuid4
from ..models.tasks import AuditLog, now_iso


def write_audit(
    session,
    task_id: str,
    event: str,
    data: dict | None = None,
    action_id: str | None = None,
    run_id: str | None = None,
    message: str | None = None,
):
    rec = AuditLog(
        id=str(uuid4()),
        task_id=task_id,
        action_id=action_id,
        run_id=run_id,
        event_type=event,
        message=message or "",
        data_json=json.dumps(data or {}),
        created_at=now_iso(),
    )
    session.add(rec)
