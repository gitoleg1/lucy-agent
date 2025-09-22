import os
from fastapi import Header, HTTPException, Request, status

AGENT_API_KEY = os.getenv("AGENT_API_KEY", "")


async def require_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-Api-Key"),
):
    token = x_api_key or request.query_params.get("apikey")
    if not token or token != AGENT_API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    return True
