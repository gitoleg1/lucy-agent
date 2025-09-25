from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, declarative_base, mapped_column, relationship

Base = declarative_base()


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


class ActionType(str, Enum):
    shell = "shell"
    http = "http"
    ssh = "ssh"
    gads = "gads"
    waha = "waha"
    browser = "browser"
    file_ops = "file_ops"


class RunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


class Decision(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def uuid_str() -> str:
    return str(uuid.uuid4())


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uuid_str)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, nullable=False, default=TaskStatus.PENDING.value)
    require_approval: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=now_iso)
    updated_at: Mapped[str] = mapped_column(String, nullable=False, default=now_iso)
    started_at: Mapped[Optional[str]] = mapped_column(String)
    ended_at: Mapped[Optional[str]] = mapped_column(String)

    actions: Mapped[List["Action"]] = relationship(
        "Action", back_populates="task", cascade="all, delete-orphan"
    )
    audits: Mapped[List["AuditLog"]] = relationship("AuditLog", back_populates="task")

    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING','WAITING_APPROVAL','APPROVED','REJECTED','RUNNING','SUCCEEDED','FAILED','CANCELED')",
            name="ck_tasks_status",
        ),
        Index("idx_tasks_status_created", "status", "created_at"),
    )


class Action(Base):
    __tablename__ = "actions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uuid_str)
    task_id: Mapped[str] = mapped_column(
        String, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    idx: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False, default=ActionType.shell.value)
    params_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=now_iso)
    updated_at: Mapped[str] = mapped_column(String, nullable=False, default=now_iso)

    task: Mapped["Task"] = relationship("Task", back_populates="actions")
    runs: Mapped[List["Run"]] = relationship(
        "Run", back_populates="action", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "type IN ('shell','http','ssh','gads','waha','browser','file_ops')",
            name="ck_actions_type",
        ),
        Index("idx_actions_task_idx", "task_id", "idx", unique=True),
    )


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uuid_str)
    action_id: Mapped[str] = mapped_column(
        String, ForeignKey("actions.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default=RunStatus.PENDING.value)
    started_at: Mapped[Optional[str]] = mapped_column(String)
    ended_at: Mapped[Optional[str]] = mapped_column(String)
    exit_code: Mapped[Optional[int]] = mapped_column(Integer)
    stdout_path: Mapped[Optional[str]] = mapped_column(Text)
    stderr_path: Mapped[Optional[str]] = mapped_column(Text)
    meta_json: Mapped[Optional[str]] = mapped_column(Text)

    action: Mapped["Action"] = relationship("Action", back_populates="runs")

    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING','RUNNING','SUCCEEDED','FAILED','CANCELED')", name="ck_runs_status"
        ),
        Index("idx_runs_action_status", "action_id", "status"),
    )


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uuid_str)
    task_id: Mapped[str] = mapped_column(
        String, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    token: Mapped[str] = mapped_column(String, nullable=False)
    decision: Mapped[Optional[str]] = mapped_column(String)
    decided_by: Mapped[Optional[str]] = mapped_column(String)
    decided_at: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=now_iso)
    expires_at: Mapped[Optional[str]] = mapped_column(String)

    task: Mapped["Task"] = relationship("Task")

    __table_args__ = (
        CheckConstraint(
            "decision IS NULL OR decision IN ('APPROVE','REJECT')", name="ck_approvals_decision"
        ),
        Index("idx_approvals_task_created", "task_id", "created_at"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uuid_str)
    task_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("tasks.id", ondelete="SET NULL")
    )
    action_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("actions.id", ondelete="SET NULL")
    )
    run_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("runs.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    data_json: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=now_iso)

    task: Mapped[Optional["Task"]] = relationship("Task", back_populates="audits")

    __table_args__ = (Index("idx_audit_task_time", "task_id", "created_at"),)
