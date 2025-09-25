from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Lucy Agent")


class Ping(BaseModel):
    message: str = "pong"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root():
    return {"hello": "world"}


@app.get("/ping")
def ping():
    return Ping().model_dump()
