"""SQLite-backed MCP Tasks extension store (io.modelcontextprotocol/tasks).

Heavy tools can return a task handle immediately; clients poll tasks/get.
Bound to auth.identity so one key cannot read another's tasks.
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
import uuid
from typing import Any, Dict, Optional

DB_PATH = os.getenv("TASKS_DB_PATH", "tasks.db")

STATUS_WORKING = "working"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"


class TaskStore:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._lock = asyncio.Lock()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                identity TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                status TEXT NOT NULL,
                result_json TEXT,
                error TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_tasks_identity ON tasks(identity);
            """
        )
        conn.commit()

    async def init_db(self) -> None:
        async with self._lock:
            conn = self._get_conn()
            try:
                self._ensure_schema(conn)
            finally:
                conn.close()

    async def create_task(self, *, identity: str, tool_name: str) -> str:
        task_id = str(uuid.uuid4())
        now = time.time()
        async with self._lock:
            conn = self._get_conn()
            try:
                self._ensure_schema(conn)
                conn.execute(
                    """INSERT INTO tasks
                       (task_id, identity, tool_name, status, result_json, error, created_at, updated_at)
                       VALUES (?, ?, ?, ?, NULL, NULL, ?, ?)""",
                    (task_id, identity, tool_name, STATUS_WORKING, now, now),
                )
                conn.commit()
            finally:
                conn.close()
        return task_id

    async def complete_task(
        self, task_id: str, *, result: Any = None, error: Optional[str] = None
    ) -> None:
        status = STATUS_FAILED if error else STATUS_COMPLETED
        result_json = None
        if result is not None:
            result_json = json.dumps(result, default=str)
        now = time.time()
        async with self._lock:
            conn = self._get_conn()
            try:
                self._ensure_schema(conn)
                conn.execute(
                    """UPDATE tasks
                       SET status = ?, result_json = ?, error = ?, updated_at = ?
                       WHERE task_id = ?""",
                    (status, result_json, error, now, task_id),
                )
                conn.commit()
            finally:
                conn.close()

    async def cancel_task(self, task_id: str, identity: str) -> bool:
        now = time.time()
        async with self._lock:
            conn = self._get_conn()
            try:
                self._ensure_schema(conn)
                cur = conn.execute(
                    """UPDATE tasks
                       SET status = ?, updated_at = ?
                       WHERE task_id = ? AND identity = ? AND status = ?""",
                    (STATUS_CANCELLED, now, task_id, identity, STATUS_WORKING),
                )
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    async def get_task(
        self, task_id: str, identity: str
    ) -> Optional[Dict[str, Any]]:
        async with self._lock:
            conn = self._get_conn()
            try:
                self._ensure_schema(conn)
                row = conn.execute(
                    """SELECT task_id, identity, tool_name, status, result_json, error,
                              created_at, updated_at
                       FROM tasks WHERE task_id = ? AND identity = ?""",
                    (task_id, identity),
                ).fetchone()
            finally:
                conn.close()
        if row is None:
            return None
        result = None
        if row["result_json"]:
            try:
                result = json.loads(row["result_json"])
            except json.JSONDecodeError:
                result = {"raw": row["result_json"]}
        return {
            "taskId": row["task_id"],
            "toolName": row["tool_name"],
            "status": row["status"],
            "result": result,
            "error": row["error"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }


# Module-level store; main.py initializes at startup.
task_store = TaskStore()

# Tools that may run asynchronously when the client supports tasks.
ASYNC_TOOL_NAMES = frozenset(
    {
        "lint_vault",
        "build_context",
        "impact_rollup",
        "graph_health",
        "get_dossier",
    }
)


def task_handle_result(task_id: str, tool_name: str) -> Dict[str, Any]:
    """Immediate tools/call result while work continues in the background."""
    payload = {
        "taskId": task_id,
        "status": STATUS_WORKING,
        "toolName": tool_name,
        "message": (
            f"Task {task_id} started for {tool_name}. "
            "Poll with tasks/get until status is completed or failed."
        ),
    }
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, indent=2),
            }
        ],
        "structuredContent": payload,
        "metadata": payload,
    }
