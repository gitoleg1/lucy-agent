from fastapi import APIRouter, Depends
from .security import require_api_key

# רוטור ייעודי ל־/stream עם הגנת API Key ברמת־ראוטר
router = APIRouter(
    prefix="/stream",
    tags=["stream"],
    dependencies=[Depends(require_api_key)],
)


@router.get("/tasks/{task_id}")
async def sse_stream(task_id: str):
    """
    Endpoint בסיסי להחזרת סטטוס/מידע על משימת streaming.
    הערה: במידת הצורך אפשר להחליף בהמשך למימוש SSE אמיתי (EventSource/StreamingResponse).
    """
    return {"task_id": task_id, "status": "ok"}
