from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .db import SessionLocal
from .models import EventLog, RunStatus, Task as TaskORM

UTC = timezone.utc


async def _log(
    session: AsyncSession, task_id: str, event_type: str, payload: Dict[str, Any] | None
):
    session.add(
        EventLog(
            task_id=task_id,
            ts=datetime.now(UTC),
            event_type=event_type,
            payload=payload or {},
        )
    )
    await session.flush()


async def run_task(task_id: str):
    """מריץ משימה (כרגע צעד shell אחד), מעדכן סטטוסים ושומר לוגים ב־DB."""
    async with SessionLocal() as session:
        # טען משימה + steps
        res = await session.execute(
            select(TaskORM)
            .options(selectinload(TaskORM.steps))
            .where(TaskORM.id == task_id)
        )
        task = res.scalar_one_or_none()
        if not task:
            return

        # התחלת משימה
        task.status = RunStatus.running.value
        task.started_at = datetime.now(UTC)
        await _log(session, task_id, "started", {"status": task.status})
        await session.commit()

        if not task.steps:
            task.status = RunStatus.failed.value
            task.ended_at = datetime.now(UTC)
            await _log(
                session, task_id, "done", {"status": task.status, "error": "no steps"}
            )
            await session.commit()
            return

        step = task.steps[0]
        step.status = RunStatus.running.value
        step.started_at = datetime.now(UTC)
        await session.commit()

        cmd = (step.params or {}).get("cmd", "")
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            await _log(session, task_id, "heartbeat", {"step_id": step.id})
            await session.commit()

            stdout_b, stderr_b = await proc.communicate()
            step.exit_code = proc.returncode
            step.stdout = (stdout_b or b"").decode(errors="replace")
            step.stderr = (stderr_b or b"").decode(errors="replace")
            step.ended_at = datetime.now(UTC)
            step.status = (
                RunStatus.succeeded.value
                if proc.returncode == 0
                else RunStatus.failed.value
            )

            task.status = step.status
            task.ended_at = datetime.now(UTC)

            await _log(
                session,
                task_id,
                "update",
                {
                    "step_id": step.id,
                    "exit_code": step.exit_code,
                    "stdout_len": len(step.stdout or ""),
                    "stderr_len": len(step.stderr or ""),
                    "status": step.status,
                },
            )
            await session.commit()

            await _log(
                session,
                task_id,
                "done",
                {
                    "status": task.status,
                    "result": {
                        "task_id": task.id,
                        "title": task.title,
                        "status": task.status,
                    },
                },
            )
            await session.commit()

        except Exception as e:
            step.status = RunStatus.failed.value
            step.ended_at = datetime.now(UTC)
            task.status = RunStatus.failed.value
            task.ended_at = datetime.now(UTC)
            await _log(
                session, task_id, "done", {"status": task.status, "error": str(e)}
            )
            await session.commit()
