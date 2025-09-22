from __future__ import annotations

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from lucy_agent.db import get_session, engine
from lucy_agent.models import Base, Task as TaskORM, Step as StepORM
from lucy_agent.orchestrator import run_task
from lucy_agent.routers import events as events_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3002",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.middleware.cors import CORSMiddleware


# CORS ל-UI מקומי

# חיבור ראוטר ה-SSE
app.include_router(events_router.router)


# יצירת טבלאות בהפעלה
@app.on_event("startup")
async def _db_startup_create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ---- Schemas
class StepCreate(BaseModel):
    type: str
    params: Dict[str, Any] = {}


class TaskCreate(BaseModel):
    title: str
    steps: List[StepCreate]


class StepOut(BaseModel):
    id: str
    type: str
    params: Dict[str, Any]
    status: str
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    exit_code: Optional[int] = None


class TaskOut(BaseModel):
    id: str
    title: str
    status: str
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    steps: List[StepOut] = []


def _task_to_out(task: TaskORM) -> TaskOut:
    return TaskOut(
        id=task.id,
        title=task.title,
        status=task.status,
        created_at=task.created_at,
        started_at=task.started_at,
        ended_at=task.ended_at,
        steps=[
            StepOut(
                id=st.id,
                type=st.type,
                params=st.params or {},
                status=st.status,
                stdout=st.stdout,
                stderr=st.stderr,
                started_at=st.started_at,
                ended_at=st.ended_at,
                exit_code=st.exit_code,
            )
            for st in (task.steps or [])
        ],
    )


# ---- Routes
@app.post("/tasks", response_model=TaskOut)
async def post_tasks(payload: TaskCreate, session: AsyncSession = Depends(get_session)):
    task_id = str(uuid.uuid4())
    t = TaskORM(
        id=task_id,
        title=payload.title,
        status="PENDING",
        created_at=datetime.utcnow(),
    )
    session.add(t)
    await session.flush()

    for s in payload.steps:
        st = StepORM(
            id=str(uuid.uuid4()),
            task_id=task_id,
            type=s.type,
            params=s.params or {},
            status="PENDING",
        )
        session.add(st)

    await session.commit()

    asyncio.create_task(run_task(task_id))

    res = await session.execute(
        select(TaskORM).where(TaskORM.id == task_id).options(selectinload(TaskORM.steps))
    )
    task = res.scalar_one()
    return _task_to_out(task)


@app.get("/tasks", response_model=List[TaskOut])
async def list_tasks(session: AsyncSession = Depends(get_session)):
    res = await session.execute(
        select(TaskORM).options(selectinload(TaskORM.steps)).order_by(TaskORM.created_at.desc())
    )
    tasks = res.scalars().unique().all()
    return [_task_to_out(t) for t in tasks]


@app.get("/tasks/{task_id}", response_model=TaskOut)
async def get_task(task_id: str, session: AsyncSession = Depends(get_session)):
    res = await session.execute(
        select(TaskORM).where(TaskORM.id == task_id).options(selectinload(TaskORM.steps))
    )
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return _task_to_out(task)
