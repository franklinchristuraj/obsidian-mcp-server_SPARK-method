"""SQLite-backed MCP Tasks extension store (multi-worker safe).

Tasks are inserted as ``queued`` with serialized args + auth. Each uvicorn
worker runs a poller that claims rows (lease), executes the tool, and
writes the result. Cancel sets status=cancelled; workers check before complete.
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

DB_PATH = os.getenv("TASKS_DB_PATH", "tasks.db")
WORKER_ID = os.getenv("MCP_WORKER_ID") or f"pid-{os.getpid()}"
LEASE_SECONDS = int(os.getenv("TASKS_LEASE_SECONDS", "120"))
POLLER_INTERVAL = float(os.getenv("TASKS_POLLER_INTERVAL", "0.5"))

STATUS_QUEUED = "queued"
STATUS_WORKING = "working"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"


class TaskStore:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._lock = asyncio.Lock()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
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
                updated_at REAL NOT NULL,
                arguments_json TEXT,
                auth_json TEXT,
                owner TEXT,
                lease_until REAL
            );
            CREATE INDEX IF NOT EXISTS idx_tasks_identity ON tasks(identity);
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            """
        )
        # Migrate older schemas
        cols = {row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
        for col, decl in (
            ("arguments_json", "TEXT"),
            ("auth_json", "TEXT"),
            ("owner", "TEXT"),
            ("lease_until", "REAL"),
        ):
            if col not in cols:
                conn.execute(f"ALTER TABLE tasks ADD COLUMN {col} {decl}")
        conn.commit()

    async def init_db(self) -> None:
        async with self._lock:
            conn = self._get_conn()
            try:
                self._ensure_schema(conn)
            finally:
                conn.close()

    async def enqueue_task(
        self,
        *,
        identity: str,
        tool_name: str,
        arguments: Dict[str, Any],
        auth: Dict[str, Any],
    ) -> str:
        """Insert a queued task for any worker to claim."""
        task_id = str(uuid.uuid4())
        now = time.time()
        async with self._lock:
            conn = self._get_conn()
            try:
                self._ensure_schema(conn)
                conn.execute(
                    """INSERT INTO tasks
                       (task_id, identity, tool_name, status, result_json, error,
                        created_at, updated_at, arguments_json, auth_json, owner, lease_until)
                       VALUES (?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?, NULL, NULL)""",
                    (
                        task_id,
                        identity,
                        tool_name,
                        STATUS_QUEUED,
                        now,
                        now,
                        json.dumps(arguments or {}, default=str),
                        json.dumps(auth, default=str),
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        return task_id

    async def create_task(self, *, identity: str, tool_name: str) -> str:
        """Backward-compat: enqueue without args (poller cannot run these)."""
        return await self.enqueue_task(
            identity=identity,
            tool_name=tool_name,
            arguments={},
            auth={"identity": identity, "allowed_scopes": [], "role": "user"},
        )

    async def claim_next(self, worker_id: str = WORKER_ID) -> Optional[Dict[str, Any]]:
        """Atomically claim the oldest queued (or stale-leased) task."""
        now = time.time()
        lease_until = now + LEASE_SECONDS
        async with self._lock:
            conn = self._get_conn()
            try:
                self._ensure_schema(conn)
                # Reclaim stale working leases back to queued
                conn.execute(
                    """UPDATE tasks SET status = ?, owner = NULL, lease_until = NULL, updated_at = ?
                       WHERE status = ? AND lease_until IS NOT NULL AND lease_until < ?""",
                    (STATUS_QUEUED, now, STATUS_WORKING, now),
                )
                row = conn.execute(
                    """SELECT task_id FROM tasks
                       WHERE status = ?
                       ORDER BY created_at ASC LIMIT 1""",
                    (STATUS_QUEUED,),
                ).fetchone()
                if row is None:
                    conn.commit()
                    return None
                task_id = row["task_id"]
                cur = conn.execute(
                    """UPDATE tasks
                       SET status = ?, owner = ?, lease_until = ?, updated_at = ?
                       WHERE task_id = ? AND status = ?""",
                    (
                        STATUS_WORKING,
                        worker_id,
                        lease_until,
                        now,
                        task_id,
                        STATUS_QUEUED,
                    ),
                )
                conn.commit()
                if cur.rowcount == 0:
                    return None
                full = conn.execute(
                    """SELECT task_id, identity, tool_name, status, arguments_json, auth_json
                       FROM tasks WHERE task_id = ?""",
                    (task_id,),
                ).fetchone()
            finally:
                conn.close()
        if full is None:
            return None
        args: Dict[str, Any] = {}
        auth: Dict[str, Any] = {}
        if full["arguments_json"]:
            try:
                args = json.loads(full["arguments_json"])
            except json.JSONDecodeError:
                args = {}
        if full["auth_json"]:
            try:
                auth = json.loads(full["auth_json"])
            except json.JSONDecodeError:
                auth = {}
        return {
            "task_id": full["task_id"],
            "identity": full["identity"],
            "tool_name": full["tool_name"],
            "arguments": args,
            "auth": auth,
        }

    async def complete_task(
        self, task_id: str, *, result: Any = None, error: Optional[str] = None
    ) -> bool:
        """Complete only if not cancelled. Returns False if cancelled/missing."""
        status = STATUS_FAILED if error else STATUS_COMPLETED
        result_json = None
        if result is not None:
            result_json = json.dumps(result, default=str)
        now = time.time()
        async with self._lock:
            conn = self._get_conn()
            try:
                self._ensure_schema(conn)
                row = conn.execute(
                    "SELECT status FROM tasks WHERE task_id = ?", (task_id,)
                ).fetchone()
                if row is None or row["status"] == STATUS_CANCELLED:
                    return False
                conn.execute(
                    """UPDATE tasks
                       SET status = ?, result_json = ?, error = ?, updated_at = ?,
                           owner = NULL, lease_until = NULL
                       WHERE task_id = ? AND status = ?""",
                    (status, result_json, error, now, task_id, STATUS_WORKING),
                )
                conn.commit()
                return True
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
                       SET status = ?, updated_at = ?, owner = NULL, lease_until = NULL
                       WHERE task_id = ? AND identity = ? AND status IN (?, ?)""",
                    (
                        STATUS_CANCELLED,
                        now,
                        task_id,
                        identity,
                        STATUS_QUEUED,
                        STATUS_WORKING,
                    ),
                )
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    async def is_cancelled(self, task_id: str) -> bool:
        async with self._lock:
            conn = self._get_conn()
            try:
                self._ensure_schema(conn)
                row = conn.execute(
                    "SELECT status FROM tasks WHERE task_id = ?", (task_id,)
                ).fetchone()
            finally:
                conn.close()
        return row is not None and row["status"] == STATUS_CANCELLED

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


task_store = TaskStore()

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
    payload = {
        "taskId": task_id,
        "status": STATUS_QUEUED,
        "toolName": tool_name,
        "message": (
            f"Task {task_id} queued for {tool_name}. "
            "Poll with tasks/get until status is completed or failed."
        ),
    }
    return {
        "content": [{"type": "text", "text": json.dumps(payload, indent=2)}],
        "structuredContent": payload,
        "metadata": payload,
    }


def auth_to_dict(ctx: Any) -> Dict[str, Any]:
    return {
        "identity": ctx.identity,
        "allowed_scopes": list(ctx.allowed_scopes),
        "role": ctx.role,
        "display_name": ctx.display_name,
        "write_scopes": list(ctx.effective_write_scopes),
    }


def auth_from_dict(data: Dict[str, Any]):
    from .scope import WorkspaceContext

    scopes = tuple(data.get("allowed_scopes") or ())
    write = data.get("write_scopes")
    return WorkspaceContext(
        identity=str(data.get("identity") or "unknown"),
        allowed_scopes=scopes,
        role=str(data.get("role") or "user"),
        display_name=str(data.get("display_name") or ""),
        write_scopes=tuple(write) if write is not None else scopes,
    )


async def run_task_poller(store: Optional[TaskStore] = None) -> None:
    """Background loop: claim queued tasks and execute tools."""
    from .mcp_server import mcp_handler
    from .scope import workspace_ctx

    store = store or task_store
    while True:
        try:
            claimed = await store.claim_next()
            if claimed is None:
                await asyncio.sleep(POLLER_INTERVAL)
                continue
            task_id = claimed["task_id"]
            tool_name = claimed["tool_name"]
            arguments = claimed["arguments"] or {}
            auth_ctx = auth_from_dict(claimed.get("auth") or {})
            token = workspace_ctx.set(auth_ctx)
            try:
                if await store.is_cancelled(task_id):
                    continue
                result = await mcp_handler._run_obsidian_tool(tool_name, arguments)
                if await store.is_cancelled(task_id):
                    continue
                await store.complete_task(task_id, result=result)
            except Exception as e:
                if not await store.is_cancelled(task_id):
                    await store.complete_task(task_id, error=str(e))
            finally:
                workspace_ctx.reset(token)
        except Exception:
            await asyncio.sleep(POLLER_INTERVAL)
