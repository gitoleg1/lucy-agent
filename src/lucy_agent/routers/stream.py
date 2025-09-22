from fastapi import Depends
from ..security import require_api_key
@app.get("/stream/tasks/{task_id}")
async def sse_stream(task_id: str, ok: bool = Depends(require_api_key)):
    ...
router = APIRouter(prefix="/stream", dependencies=[Depends(require_api_key)])
@router.get("/tasks/{task_id}")
async def sse_stream(task_id: str):
    ...
from .security import require_api_key
from fastapi import Depends

app.include_router(stream_router, dependencies=[Depends(require_api_key)])
