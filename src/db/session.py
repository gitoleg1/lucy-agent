import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def _db_path() -> str:
    p = os.environ.get(
        "LUCY_DB_PATH", str(Path.home() / ".local" / "share" / "lucy-agent.db")
    )
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    return p


_engine = create_engine(f"sqlite:///{_db_path()}", echo=False, future=True)
SessionLocal = sessionmaker(
    bind=_engine, autoflush=False, autocommit=False, future=True
)


def get_session():
    return SessionLocal()
