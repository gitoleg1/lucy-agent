from __future__ import annotations

from fastapi import FastAPI

# Router קיים של המשימות (כבר בשימוש אצלך)
from routers.tasks import router as tasks_router  # type: ignore

# כאן אנחנו מוסיפים גם את ה-Router של האירועים/אוטופיילוט שבו יושבים /quick-run ו-/agent/shell
from lucy_agent.routers import events as events_router


def create_app() -> FastAPI:
    app = FastAPI(title="Lucy Agent API", version="0.1.0")

    # בריאות/גרסה בסיסיים (נשארים כפי שהיו)
    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/version")
    def version() -> dict[str, str]:
        return {"version": "0.1.0"}

    # Include routers
    app.include_router(events_router.router)  # ← כאן נכנסים /quick-run ו-/agent/shell
    app.include_router(tasks_router)

    return app


app = create_app()
