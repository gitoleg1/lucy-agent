from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.inspection import inspect as sa_inspect

from ..db.session import get_session
from ..models.tasks import (
    Action,
    Approval,
    AuditLog,
    Run,
    Task,
    TaskStatus,
    now_iso,
)
from ..services.audit import write_audit


def _fix_timeout_semantics(result):
    """
    מנרמל תוצאת quick_run כך ש-timeout יחזור בקוד יציאה תקני
    ועם שדות audit תקינים (timeout=true, tails כ-strings).
    עובד גם כשמחזירים מודל של Pydantic וגם dict.
    """
    try:
        # פרק לאובייקט dict
        if hasattr(result, "model_dump"):
            data = result.model_dump()
        elif hasattr(result, "dict"):
            data = result.dict()
        else:
            data = result

        if not isinstance(data, dict):
            return result

        runs = data.get("runs") or []
        audit = data.get("audit") or []

        try:
            import os

            timeout_exit = int(os.getenv("LUCY_AUTOPILOT_TIMEOUT_EXIT", "124"))
        except Exception:
            timeout_exit = 124

        # בנה מיפוי action_id -> אירועי action_end
        end_by_action = {}
        for ev in audit:
            try:
                if ev.get("event") == "action_end":
                    aid = ev.get("data", {}).get("action_id")
                    if aid:
                        end_by_action.setdefault(aid, []).append(ev)
            except Exception:
                pass

        # נרמל כל run עם exit_code == -1 (timeout ישן)
        for r in runs:
            try:
                if r.get("exit_code") == -1:
                    r["exit_code"] = timeout_exit
                    aid = r.get("action_id")
                    if aid and aid in end_by_action:
                        for ev in end_by_action[aid]:
                            evd = ev.setdefault("data", {})
                            evd["timeout"] = True
                            if evd.get("stdout_tail") is None:
                                evd["stdout_tail"] = ""
                            if evd.get("stderr_tail") is None:
                                evd["stderr_tail"] = ""
                            evd["exit_code"] = r["exit_code"]
            except Exception:
                pass

        return data
    except Exception:
        # במקרה של תקלה – החזר את המקור כדי לא להפיל את ה-API
        return result


router = APIRouter(prefix="/tasks", tags=["tasks"])


# ===== Schemas =====
class ActionIn(BaseModel):
    type: Literal["shell"] = "shell"
    params: Dict[str, Any] = Field(default_factory=dict)


class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    require_approval: bool = False
    actions: List[ActionIn] = Field(default_factory=list)


class ApprovalIn(BaseModel):
    token: str
    decision: Literal["APPROVE", "REJECT"]
    decided_by: str


class RunOut(BaseModel):
    id: str
    task_id: str
    action_id: str
    status: str
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    stdout_path: Optional[str] = None
    stderr_path: Optional[str] = None
    exit_code: Optional[int] = None


class AuditOut(BaseModel):
    id: str
    task_id: str
    event: str
    data: Dict[str, Any] = Field(default_factory=dict)
    created_at: str


class TaskOut(BaseModel):
    id: str
    title: str
    description: Optional[str]
    status: str
    require_approval: int
    created_at: str
    updated_at: str
    started_at: Optional[str]
    ended_at: Optional[str]
    approvals: List[Dict[str, Any]] = Field(default_factory=list)


# ===== Helpers =====
RUNS_BASE = Path.home() / ".local" / "share" / "lucy-agent" / "runs"
RUNS_BASE.mkdir(parents=True, exist_ok=True)


def _task_to_out(s, task: Task) -> TaskOut:
    approvals: List[Dict[str, Any]] = []
    try:
        aps = s.execute(select(Approval).where(Approval.task_id == task.id)).scalars().all()
        for a in aps:
            approvals.append(
                {
                    "id": a.id,
                    "task_id": a.task_id,
                    "token": a.token,
                    "decision": a.decision,
                    "decided_by": a.decided_by,
                    "decided_at": a.decided_at,
                    "created_at": a.created_at,
                    "expires_at": a.expires_at,
                }
            )
    except Exception:
        approvals = []

    return TaskOut(
        id=task.id,
        title=task.title,
        description=task.description,
        status=task.status,
        require_approval=task.require_approval,
        created_at=task.created_at,
        updated_at=task.updated_at,
        started_at=task.started_at,
        ended_at=task.ended_at,
        approvals=approvals,
    )


# ===== Endpoints =====


@router.post("/", response_model=TaskOut)
def create_task(payload: TaskCreate):
    # מחרוזות סטטוס כדי לא להיות תלויים ב-Enum ספציפי
    status_value = "WAITING_APPROVAL" if payload.require_approval else "PENDING"
    now = now_iso()
    with get_session() as s:
        # Task
        task = Task(
            id=str(uuid4()),
            title=payload.title,
            description=payload.description,
            status=status_value,
            require_approval=1 if payload.require_approval else 0,
            created_at=now,
            updated_at=now,
            started_at=None,
            ended_at=None,
        )
        s.add(task)
        safe_commit(s)

        # Approval (אם נדרש)
        if payload.require_approval:
            ap = Approval(
                id=str(uuid4()),
                task_id=task.id,
                token=str(uuid4()),
                decision=None,
                decided_by=None,
                decided_at=None,
                created_at=now,
                expires_at=None,
            )
            s.add(ap)

        # Actions עם idx (פותר NOT NULL על actions.idx)
        for i, a in enumerate(payload.actions or []):
            params_json = json.dumps(a.params or {})
            act = Action(
                id=str(uuid4()),
                task_id=task.id,
                idx=i,
                type=a.type,
                params_json=params_json,
                created_at=now,
                updated_at=now,
            )
            s.add(act)

        safe_commit(s)

        # Audit
        write_audit(
            s,
            task_id=task.id,
            event="task_created",
            data={
                "title": task.title,
                "require_approval": bool(task.require_approval),
                "actions_count": len(payload.actions or []),
            },
        )

        return _task_to_out(s, task)


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: str):
    with get_session() as s:
        t = s.execute(select(Task).where(Task.id == task_id)).scalars().first()
        if not t:
            raise HTTPException(status_code=404, detail="Task not found")
        return _task_to_out(s, t)


@router.post("/{task_id}/approve", response_model=TaskOut)
def approve_task(task_id: str, body: ApprovalIn):
    with get_session() as s:
        t = s.execute(select(Task).where(Task.id == task_id)).scalars().first()
        if not t:
            raise HTTPException(status_code=404, detail="Task not found")

        ap = s.execute(select(Approval).where(Approval.task_id == task_id)).scalars().first()
        if not ap or ap.token != body.token:
            raise HTTPException(status_code=400, detail="Invalid approval token")

        ap.decision = body.decision
        ap.decided_by = body.decided_by
        ap.decided_at = now_iso()
        t.status = "APPROVED" if body.decision == "APPROVE" else TaskStatus.REJECTED
        t.updated_at = now_iso()

        write_audit(
            s,
            task_id=task_id,
            event="approval_decided",
            data={"decision": body.decision, "by": body.decided_by},
            message="approval decided",
        )

        safe_commit(s)
        return _task_to_out(s, t)


@router.post("/{task_id}/run", response_model=List[RunOut])
def run_task(task_id: str):
    with get_session() as s:
        t = s.execute(select(Task).where(Task.id == task_id)).scalars().first()
        if not t:
            raise HTTPException(status_code=404, detail="Task not found")

        if t.require_approval and t.status != "APPROVED":
            raise HTTPException(status_code=400, detail="Task requires approval")

        acts = s.execute(select(Action).where(Action.task_id == task_id)).scalars().all()
        if not acts:
            raise HTTPException(status_code=400, detail="No actions to run")

        results: List[RunOut] = []

        for a in acts:
            if a.type != "shell":
                raise HTTPException(status_code=400, detail=f"Unsupported action type: {a.type}")

            params = json.loads(a.params_json or "{}")
            cmd = params.get("cmd")
            if not cmd:
                raise HTTPException(status_code=400, detail="shell action missing 'cmd'")

            run_id = str(uuid4())
            run_dir = RUNS_BASE / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            stdout_p = run_dir / "stdout.log"
            stderr_p = run_dir / "stderr.log"

            r = Run(
                id=run_id,
                action_id=a.id,
                status="RUNNING",
                started_at=now_iso(),
                ended_at=None,
                exit_code=None,
                stdout_path=str(stdout_p),
                stderr_path=str(stderr_p),
            )
            s.add(r)
            safe_commit(s)

            write_audit(
                s,
                task_id=task_id,
                event="action_start",
                data={"action_id": a.id, "type": a.type, "cmd": cmd},
                run_id=run_id,
                action_id=a.id,
                message="action started",
            )

            try:
                with open(stdout_p, "wb") as out, open(stderr_p, "wb") as err:
                    proc = subprocess.run(
                        cmd,
                        shell=True,
                        stdout=out,
                        stderr=err,
                        cwd=os.path.expanduser("~"),
                    )
                exit_code = int(proc.returncode)
                r.exit_code = exit_code
                r.status = "SUCCEEDED" if r.exit_code == 0 else "FAILED"
                r.ended_at = now_iso()
                safe_commit(s)

                write_audit(
                    s,
                    task_id=task_id,
                    event="action_end",
                    data={"action_id": a.id, "exit_code": exit_code},
                    run_id=run_id,
                    action_id=a.id,
                    message="action ended",
                )

            except Exception as e:
                r.status = "FAILED"
                r.ended_at = now_iso()
                r.exit_code = -1
                safe_commit(s)

                write_audit(
                    s,
                    task_id=task_id,
                    event="action_error",
                    data={"action_id": a.id, "error": repr(e)},
                    run_id=run_id,
                    action_id=a.id,
                    message=f"action error: {e!r}",
                )

            results.append(
                RunOut(
                    id=r.id,
                    task_id=task_id,
                    action_id=r.action_id,
                    status=r.status,
                    started_at=r.started_at,
                    ended_at=r.ended_at,
                    stdout_path=r.stdout_path,
                    stderr_path=r.stderr_path,
                    exit_code=r.exit_code,
                )
            )

        t.status = "FAILED" if any(ro.status == "FAILED" for ro in results) else "SUCCEEDED"
        t.updated_at = now_iso()
        safe_commit(s)

        return results


@router.get("/{task_id}/audit", response_model=List[AuditOut])
def get_audit(task_id: str):
    with get_session() as s:
        rows = (
            s.execute(
                select(AuditLog)
                .where(AuditLog.task_id == task_id)
                .order_by(AuditLog.created_at.asc())
            )
            .scalars()
            .all()
        )

        out: List[AuditOut] = []
        for r in rows:
            event = (
                getattr(r, "event_type", None)
                or getattr(r, "event", None)
                or getattr(r, "type", None)
                or "event"
            )
            raw = getattr(r, "data_json", None) or getattr(r, "data", None)
            try:
                data = json.loads(raw) if isinstance(raw, str) else (raw or {})
            except Exception:
                data = {}
            out.append(
                AuditOut(
                    id=r.id,
                    task_id=task_id,
                    event=event,
                    data=data,
                    created_at=r.created_at,
                )
            )
        return out


# --- local commit helper ---
def safe_commit(s) -> None:
    """Commit and roll back on error; small local helper for this router."""
    try:
        s.commit()
    except Exception:
        try:
            s.rollback()
        except Exception:
            pass
        raise


# >>> LUCY_AUTOPILOT_QUICK_RUN_BEGIN
# ========= Lucy Autopilot — QuickRun & Agent Shell (Guardrails v1) =========


# ------------------ Helpers קיימים (השארנו כפי שהיו) ------------------
def _cols(cls):
    try:
        return {c.key for c in sa_inspect(cls).columns}
    except Exception:
        return set()


def _json_parse(val):
    if isinstance(val, dict):
        return val
    if isinstance(val, (bytes, bytearray)):
        try:
            return json.loads(val.decode("utf-8", "ignore"))
        except Exception:
            return {"raw": val.decode("utf-8", "ignore", errors="ignore")}
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return {"raw": val}
    return None


def _tail_bytes(path: Optional[str], limit: int = 400) -> Optional[str]:
    if not path:
        return None
    try:
        p = Path(path)
        if not p.exists() or not p.is_file():
            return None
        size = p.stat().st_size
        with open(p, "rb") as f:
            if size > limit:
                f.seek(-limit, os.SEEK_END)
            data = f.read()
        try:
            return data.decode("utf-8", "ignore")
        except Exception:
            return data.decode("latin-1", "ignore")
    except Exception:
        return None


# ------------------ Guardrails הגדרות ------------------
_AUTOPILOT_TOKEN = os.environ.get("LUCY_AUTOPILOT_TOKEN", "").strip()
_TIMEOUT_SEC = int(os.environ.get("LUCY_AUTOPILOT_TIMEOUT_SECONDS", "30"))
_MIN_INTERVAL_SEC = float(os.environ.get("LUCY_AUTOPILOT_MIN_INTERVAL_SEC", "1.0"))
_RATE_FILE = Path(os.environ.get("LUCY_AUTOPILOT_RATE_FILE", "/tmp/lucy_autopilot.rate"))

# Allow/Deny (מחרוזות; allow כ-prefixים, deny כ-substrings)
_DEFAULT_DENY = [
    "rm -rf /",
    "mkfs",
    ">:(){:|:&};:",
    ":(){:|:&};:",  # fork-bomb
    "dd if=",
    " of=/dev/sd",
    "mkpartition",
    "fdisk",
    "parted",
    "shutdown",
    "reboot",
    "poweroff",
    "chown -R /",
    "chmod -R /",
    "userdel ",
    "groupdel ",
    "mount ",
    "umount ",
    "curl | sh",
    "curl|sh",
    "wget -O- | sh",
    "wget -qO- | sh",
]
_ALLOW_PREFIXES = [
    p.strip() for p in os.environ.get("LUCY_AUTOPILOT_ALLOW", "").split(",") if p.strip()
]
_DENY_SUBSTR = [
    d.strip() for d in os.environ.get("LUCY_AUTOPILOT_DENY", "").split(",") if d.strip()
] or _DEFAULT_DENY


def _auth_check(req: Request):
    if not _AUTOPILOT_TOKEN:
        # אם אין טוקן בהגדרות — לא מחייבים כרגע (MVP). ל-Hardening הפוך ל-Required.
        return
    hdr = req.headers.get("x-api-key", "") or req.headers.get("authorization", "").replace(
        "Bearer ", ""
    )
    if hdr != _AUTOPILOT_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _rate_limit():
    try:
        now = time.time()
        if _RATE_FILE.exists():
            last = float(_RATE_FILE.read_text() or "0")
            if now - last < _MIN_INTERVAL_SEC:
                raise HTTPException(status_code=429, detail="Too Many Requests")
        _RATE_FILE.write_text(str(now))
    except HTTPException:
        raise
    except Exception:
        # לא מפיל בקשה אם יש שגיאת קובץ; ממשיך
        pass


def _allow_deny_check(cmd: str):
    c = cmd.strip()
    # אם מוגדר Allow — צריך לעבור אחד מהם (prefix)
    if _ALLOW_PREFIXES:
        if not any(c.startswith(p) for p in _ALLOW_PREFIXES):
            raise HTTPException(status_code=400, detail="Command not allowed by policy (allowlist)")
    # Deny substrings
    low = c.lower()
    for bad in _DENY_SUBSTR:
        if bad and bad.lower() in low:
            raise HTTPException(status_code=400, detail=f"Command blocked by denylist: {bad}")


def _resource_limiter():
    # יחול על תהליך הצאצא (Linux בלבד)
    try:
        import resource

        def _set():
            try:
                # CPU seconds
                resource.setrlimit(resource.RLIMIT_CPU, (_TIMEOUT_SEC, _TIMEOUT_SEC))
            except Exception:
                pass
            try:
                # זיכרון (כתובת וירטואלית) ~ 512MB ברירת מחדל
                mem = int(os.environ.get("LUCY_AUTOPILOT_MAX_AS_MB", "512")) * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
            except Exception:
                pass
            try:
                # גודל קובץ פלט מקס' 32MB
                fs = int(os.environ.get("LUCY_AUTOPILOT_MAX_FSIZE_MB", "32")) * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_FSIZE, (fs, fs))
            except Exception:
                pass

        return _set
    except Exception:
        return None


# ------------------ סכימות I/O ------------------
class QuickRunIn(BaseModel):
    title: str = "autopilot"
    actions: List[ActionIn]


class QuickRunOut(BaseModel):
    task: TaskOut
    runs: List[RunOut]
    audit: List[AuditOut]


# ------------------ Quick Run ------------------
@router.post("/quick-run", response_model=QuickRunOut)
def quick_run(payload: QuickRunIn, request: Request):
    _auth_check(request)
    _rate_limit()

    # 1) Task חדש (Auto-approve)
    T = _cols(Task)
    t_kwargs = {}
    if "id" in T:
        t_kwargs["id"] = str(uuid4())
    if "title" in T:
        t_kwargs["title"] = payload.title
    if "description" in T:
        t_kwargs["description"] = None
    if "status" in T:
        t_kwargs["status"] = (
            TaskStatus.PENDING.value if hasattr(TaskStatus, "PENDING") else "PENDING"
        )
    if "require_approval" in T:
        t_kwargs["require_approval"] = False
    if "created_at" in T:
        t_kwargs["created_at"] = now_iso()
    if "updated_at" in T:
        t_kwargs["updated_at"] = now_iso()

    t = Task(**t_kwargs)
    with get_session() as s:
        s.add(t)
        safe_commit(s)
        write_audit(
            s,
            getattr(t, "id", None),
            "task_created",
            {
                "title": getattr(t, "title", None),
                "require_approval": getattr(t, "require_approval", False),
            },
        )

    # 2) פעולות (idx/params_json)
    with get_session() as s:
        t_db = s.scalar(select(Task).where(Task.id == getattr(t, "id", None)))
        if not t_db:
            raise HTTPException(status_code=404, detail="Task not found")

        A = _cols(Action)
        for a in payload.actions:
            next_idx = 1
            if "idx" in A:
                max_idx = s.scalar(
                    select(func.max(Action.idx)).where(Action.task_id == getattr(t_db, "id", None))
                )
                next_idx = (max_idx or 0) + 1

            cmd = None
            try:
                if getattr(a, "params", None):
                    cmd = (a.params or {}).get("cmd")
            except Exception:
                cmd = None

            # Allow/Deny עוד לפני שמכניסים ל-DB
            if cmd:
                _allow_deny_check(cmd)

            a_kwargs = {}
            if "id" in A:
                a_kwargs["id"] = str(uuid4())
            if "task_id" in A:
                a_kwargs["task_id"] = getattr(t_db, "id", None)
            if "idx" in A:
                a_kwargs["idx"] = next_idx
            if "type" in A:
                a_kwargs["type"] = a.type
            if "created_at" in A:
                a_kwargs["created_at"] = now_iso()
            if "updated_at" in A:
                a_kwargs["updated_at"] = now_iso()
            if "params_json" in A:
                a_kwargs["params_json"] = json.dumps({"cmd": cmd} if cmd is not None else {})

            s.add(Action(**a_kwargs))
        safe_commit(s)

    # 3) ריצה לפי idx/id + resource/timeout
    run_results: List[RunOut] = []
    with get_session() as s:
        A = _cols(Action)
        order_clause = Action.idx if "idx" in A else Action.id
        acts = s.scalars(
            select(Action).where(Action.task_id == getattr(t, "id", None)).order_by(order_clause)
        ).all()

        if not acts:
            if hasattr(t, "status"):
                t.status = "SUCCEEDED"
            if hasattr(t, "updated_at"):
                t.updated_at = now_iso()
            safe_commit(s)
        else:
            preexec = _resource_limiter()
            for act in acts:
                R = _cols(Run)
                r_kwargs = {}
                if "id" in R:
                    r_kwargs["id"] = str(uuid4())
                if "action_id" in R:
                    r_kwargs["action_id"] = getattr(act, "id", None)
                if "status" in R:
                    r_kwargs["status"] = "RUNNING"
                if "started_at" in R:
                    r_kwargs["started_at"] = now_iso()

                r = Run(**r_kwargs)
                s.add(r)
                safe_commit(s)

                # שליפת cmd
                cmd_val = None
                if "params_json" in A:
                    try:
                        raw = getattr(act, "params_json", None)
                        if isinstance(raw, (bytes, bytearray)):
                            raw = raw.decode("utf-8", "ignore")
                        obj = json.loads(raw or "{}") if isinstance(raw, str) else (raw or {})
                        if isinstance(obj, dict):
                            cmd_val = obj.get("cmd")
                    except Exception:
                        cmd_val = None

                write_audit(
                    s,
                    getattr(t, "id", None),
                    "action_start",
                    {
                        "action_id": getattr(act, "id", None),
                        "type": getattr(act, "type", None),
                        "cmd": cmd_val,
                    },
                )

                try:
                    if getattr(act, "type", None) != "shell":
                        raise RuntimeError(f"Unsupported action type: {getattr(act, 'type', None)}")
                    if not cmd_val:
                        raise RuntimeError("Missing shell cmd")

                    # בדיקת allow/deny בשלב הריצה (שוב, למקרה של שינוי)
                    _allow_deny_check(cmd_val)

                    run_dir = Path(
                        os.environ.get(
                            "LUCY_RUNS_DIR", str(Path.home() / ".local/share/lucy-agent/runs")
                        )
                    ) / (getattr(r, "id", "run"))
                    run_dir.mkdir(parents=True, exist_ok=True)
                    stdout_path = run_dir / "stdout.log"
                    stderr_path = run_dir / "stderr.log"

                    with open(stdout_path, "wb") as out, open(stderr_path, "wb") as err:
                        subprocess.run(
                            cmd_val,
                            shell=True,
                            stdout=out,
                            stderr=err,
                            timeout=_TIMEOUT_SEC,
                            preexec_fn=preexec,
                        )

                    # עדכון סטטוס לפי קוד חזרה מתוך stderr/stdout? נשתמש בקובץ ה-exit_code אם קיים או ב-0/חריג.
                    # כאן, אם subprocess.run לא זרק — הקוד 0; אחרת ב-except.
                    if hasattr(r, "stdout_path"):
                        r.stdout_path = str(stdout_path)
                    if hasattr(r, "stderr_path"):
                        r.stderr_path = str(stderr_path)
                    if hasattr(r, "exit_code"):
                        r.exit_code = 0
                    if hasattr(r, "status"):
                        r.status = "SUCCEEDED"
                    if hasattr(r, "ended_at"):
                        r.ended_at = now_iso()
                    safe_commit(s)

                    tail_out = _tail_bytes(getattr(r, "stdout_path", None), 400)
                    tail_err = _tail_bytes(getattr(r, "stderr_path", None), 400)
                    write_audit(
                        s,
                        getattr(t, "id", None),
                        "action_end",
                        {
                            "action_id": getattr(act, "id", None),
                            "exit_code": getattr(r, "exit_code", None),
                            "stdout_tail": tail_out,
                            "stderr_tail": tail_err,
                        },
                    )

                except subprocess.TimeoutExpired:
                    if hasattr(r, "exit_code"):
                        r.exit_code = -1
                    if hasattr(r, "status"):
                        r.status = "FAILED"
                    if hasattr(r, "ended_at"):
                        r.ended_at = now_iso()
                    safe_commit(s)
                    write_audit(
                        s,
                        getattr(t, "id", None),
                        "action_end",
                        {
                            "action_id": getattr(act, "id", None),
                            "exit_code": -1,
                            "error": f"timeout({_TIMEOUT_SEC}s)",
                            "stdout_tail": _tail_bytes(getattr(r, "stdout_path", None), 400),
                            "stderr_tail": _tail_bytes(getattr(r, "stderr_path", None), 400),
                        },
                    )

                except Exception as e:
                    # במצב זה אין לנו exit_code סיסטמי; ננסה לדגום דרך קובץ/ניתוח — ל-MVP נשים -2 כברירת מחדל.
                    if hasattr(r, "exit_code"):
                        r.exit_code = -2
                    if hasattr(r, "status"):
                        r.status = "FAILED"
                    if hasattr(r, "ended_at"):
                        r.ended_at = now_iso()
                    safe_commit(s)
                    write_audit(
                        s,
                        getattr(t, "id", None),
                        "action_end",
                        {
                            "action_id": getattr(act, "id", None),
                            "exit_code": getattr(r, "exit_code", None),
                            "error": str(e),
                            "stdout_tail": _tail_bytes(getattr(r, "stdout_path", None), 400),
                            "stderr_tail": _tail_bytes(getattr(r, "stderr_path", None), 400),
                        },
                    )

                run_results.append(
                    RunOut(
                        id=getattr(r, "id", ""),
                        task_id=str(getattr(t, "id", "")),
                        action_id=getattr(r, "action_id", None),
                        status=getattr(r, "status", None),
                        started_at=getattr(r, "started_at", None),
                        ended_at=getattr(r, "ended_at", None),
                        stdout_path=getattr(r, "stdout_path", None),
                        stderr_path=getattr(r, "stderr_path", None),
                        exit_code=getattr(r, "exit_code", None),
                    )
                )

            # סטטוס task מסיכום הריצות
            with get_session() as s2:
                t_db2 = s2.scalar(select(Task).where(Task.id == getattr(t, "id", None)))
                if t_db2 and hasattr(t_db2, "status"):
                    t_db2.status = "FAILED" if any(getattr(ro, "status", None) == "FAILED" for ro in run_results) else "SUCCEEDED"
                if t_db2 and hasattr(t_db2, "updated_at"):
                    t_db2.updated_at = now_iso()
                safe_commit(s2)

    # 4) Audit לפי created_at + המרת data ל-dict (ונשמר ה-fallback הסינתטי אם חסר end)
    with get_session() as s:
        try:
            aud_q = (
                select(AuditLog)
                .where(AuditLog.task_id == getattr(t, "id", None))
                .order_by(AuditLog.created_at)
            )
        except Exception:
            aud_q = select(AuditLog).where(AuditLog.task_id == getattr(t, "id", None))
        auds = s.scalars(aud_q).all()

        audit_out = []
        for a in auds:
            data_raw = getattr(a, "data", None) or getattr(a, "data_json", None)
            audit_out.append(
                AuditOut(
                    id=getattr(a, "id", None),
                    task_id=getattr(a, "task_id", None),
                    event=getattr(a, "event", getattr(a, "event_type", None)),
                    data=_json_parse(data_raw),
                    created_at=getattr(a, "created_at", None),
                )
            )

        have_end = any(getattr(x, "event", None) == "action_end" for x in audit_out)
        if not have_end and run_results:
            for ro in run_results:
                audit_out.append(
                    AuditOut(
                        id=str(uuid4()),
                        task_id=ro.task_id,
                        event="action_end",
                        data={
                            "action_id": ro.action_id,
                            "exit_code": ro.exit_code,
                            "stdout_tail": _tail_bytes(getattr(ro, "stdout_path", None), 400),
                            "stderr_tail": _tail_bytes(getattr(ro, "stderr_path", None), 400),
                            "synthetic": True,
                        },
                        created_at=now_iso(),
                    )
                )

    # 5) TaskOut עדכני
    with get_session() as s:
        t_final = s.scalar(select(Task).where(Task.id == getattr(t, "id", None)))
        task_out = _task_to_out(s, t_final)

    return _fix_timeout_semantics(QuickRunOut(task=task_out, runs=run_results, audit=audit_out))


# ------------------ Agent Shell ------------------
class AgentShellIn(BaseModel):
    cmd: str
    title: Optional[str] = "agent-shell"


@router.post("/agent/shell", response_model=QuickRunOut)
def agent_shell(payload: AgentShellIn, request: Request):
    _auth_check(request)
    return quick_run(
        QuickRunIn(
            title=payload.title or "agent-shell",
            actions=[ActionIn(type="shell", params={"cmd": payload.cmd})],
        ),
        request=request,
    )


# ========= סוף Lucy Autopilot (Guardrails v1) =========
# <<< LUCY_AUTOPILOT_QUICK_RUN_END
