from .routers.tasks import router as tasks_router
from fastapi import FastAPI
from fastapi.responses import JSONResponse

# === בריאות בסיסית ===
app = FastAPI(title="Lucy Agent API", version="0.1.0")


@app.get("/health", summary="Health")
def health():
    return JSONResponse({"status": "ok"})


# === Routers ===
# חשוב: זה ה־router שמגדיר /tasks עם actions (לא steps)

app.include_router(tasks_router)
