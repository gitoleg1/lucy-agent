# src/lucy_agent/main.py
from fastapi import FastAPI

app = FastAPI(title="Lucy Agent")


@app.get("/health")
def health():
    return {"status": "ok"}
