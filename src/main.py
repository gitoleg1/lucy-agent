from __future__ import annotations

import importlib
import inspect
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.requests import Request

try:
    from loguru import logger  # type: ignore
except Exception:
    import logging

    logger = logging.getLogger("lucy-agent")
    if not logger.handlers:
        logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Lucy-Agent Service", version="0.1.0")


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"status": False, "output": "", "error": str(exc)})


@app.on_event("startup")
async def startup():
    try:
        db_mod = importlib.import_module("src.db")
        init_db = getattr(db_mod, "init_db", None)
        if callable(init_db):
            res = init_db()
            if inspect.isawaitable(res):
                await res
        logger.info("Lucy-Agent startup complete.")
    except Exception as e:
        logger.warning(f"DB init skipped: {e}")


@app.get("/health")
def health():
    return {"status": "ok"}


def _include_router_safe(module_path: str, prefix: str = "/actions", tag: str = "actions"):
    try:
        mod = importlib.import_module(module_path)
        router = getattr(mod, "router", None)
        if router is None:
            raise AttributeError(f"router not found in {module_path}")
        app.include_router(router, prefix=prefix, tags=[tag])
        logger.info(f"Router loaded: {module_path} → {prefix}")
    except Exception as e:
        logger.warning(f"Router NOT loaded ({module_path}): {e}")


_include_router_safe("src.actions.echo")
_include_router_safe("src.actions.ssh")
_include_router_safe("src.actions.pwsh")
_include_router_safe("src.actions.shell")
_include_router_safe("src.actions.http")
_include_router_safe("src.actions.browser")
_include_router_safe("src.actions.logs")
_include_router_safe("src.actions.waha")
_include_router_safe("src.actions.gads")

# קיצור אופציונלי ללא prefix:
try:
    from src.actions import ssh as _ssh

    app.include_router(_ssh.router, prefix="")
except Exception:
    pass
