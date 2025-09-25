from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

DATA_DIR = os.path.expanduser("~/projects/lucy-agent/data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_URL = f"sqlite+aiosqlite:///{os.path.join(DATA_DIR, 'agent.db')}"

engine = create_async_engine(DB_URL, echo=False, future=True)
SessionLocal = async_sessionmaker(
    bind=engine, expire_on_commit=False, autoflush=False, autocommit=False
)
Base = declarative_base()


async def get_session() -> AsyncSession:
    async with SessionLocal() as session:
        yield session
