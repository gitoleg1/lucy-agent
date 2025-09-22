from fastapi import APIRouter, Query
import aiosqlite
import os

router = APIRouter()
DB_PATH = os.getenv("LUCY_AGENT_DB", "lucy_agent.db")


@router.get("/logs/recent")
async def recent_logs(limit: int = Query(20, ge=1, le=200)):
    rows = []
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, ts, action, input, output, status FROM task_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ) as cur:
            async for r in cur:
                rows.append(
                    {
                        "id": r[0],
                        "ts": r[1],
                        "action": r[2],
                        "input": r[3],
                        "output": r[4],
                        "status": r[5],
                    }
                )
    return {"items": rows}
