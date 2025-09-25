import os
from functools import lru_cache

from pydantic import BaseModel


class Settings(BaseModel):
    port: int = int(os.getenv("PORT", "8000"))
    api_key: str = os.getenv("AGENT_API_KEY", "ChangeMe_SuperSecret_Long")
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()


@lru_cache
def get_settings() -> Settings:
    return Settings()
