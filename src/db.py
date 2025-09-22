import aiosqlite
import os

DB_PATH = os.getenv("LUCY_AGENT_DB", "lucy_agent.db")

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS task_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts DATETIME DEFAULT CURRENT_TIMESTAMP,
            action TEXT NOT NULL,
            input TEXT,
            output TEXT,
            status TEXT
        )
        """)
        await db.commit()

async def log_action(action: str, input_: str, output: str, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO task_log(action, input, output, status) VALUES(?,?,?,?)",
            (action, input_, output, status),
        )
        await db.commit()
