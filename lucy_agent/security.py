import os
from fastapi import Header, HTTPException, Depends, Request, status

API_KEY_ENV = "AGENT_API_KEY"


def get_api_key_header(
    x_api_key: str | None = Header(default=None, alias="X-Api-Key")
) -> str | None:
    return x_api_key


def get_api_key_query(request: Request) -> str | None:
    return request.query_params.get("apikey") or request.query_params.get("api_key")


def require_api_key(
    header_key: str | None = Depends(get_api_key_header),
    query_key: str | None = Depends(get_api_key_query),
):
    expected = os.getenv(API_KEY_ENV, "")
    provided = header_key or query_key
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="API key not configured"
        )
    if not provided or provided != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    return True
