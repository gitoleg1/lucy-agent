import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import events as events_router

def _origins_from_env() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "")
    return [o.strip() for o in raw.split(",") if o.strip()]

app = FastAPI(title="Lucy Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins_from_env() or ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(events_router.router)
