"""
In-process tool-call observability (Ziksaka).

Logs every tools/call to a local SQLite file so tool-selection behavior
(redundant calls, wrong tool, dead tools) can be reviewed after the fact.
Writes never happen on the request path: log_tool_call() only enqueues,
a background task drains the queue and flushes to SQLite.

Correlation (2026-07-28): protocol sessions are gone. Each request gets a
correlation id — optional Mcp-Session-Id if the client still sends one,
else a per-request UUID. Client type comes from _meta clientInfo (modern)
or a legacy initialize registration keyed by echoed correlation id.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
import time
import uuid
from collections import OrderedDict
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

DB_PATH = os.getenv("OBS_DB_PATH", "observability.db")
REDACT_ARGS = os.getenv("REDACT_ARGS", "true").strip().lower() not in ("false", "0", "no")

SESSION_FALLBACK_WINDOW_SECONDS = 30
_QUEUE_MAXSIZE = 1000
_BATCH_MAX = 100

_queue: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
_dropped_count = 0

# correlation_id -> classified client ("Desktop" | "Code" | "n8n" | "unknown"),
# populated from clientInfo.name on legacy `initialize` only. Bounded LRU.
_SESSION_CLIENTS_MAX = 10_000
_session_clients: "OrderedDict[str, str]" = OrderedDict()


@dataclass(frozen=True)
class CallContext:
    """Request-scoped observability context.

    ``session_id`` is the correlation id stored in SQLite (column name kept
    for compatibility). Prefer reading ``correlation_id`` via the property.
    """

    session_id: str
    client: str

    @property
    def correlation_id(self) -> str:
        return self.session_id


call_context: ContextVar[Optional[CallContext]] = ContextVar("call_context", default=None)


def _classify_client(raw_name: Optional[str]) -> str:
    if not raw_name:
        return "unknown"
    name = raw_name.lower()
    if "desktop" in name:
        return "Desktop"
    if "code" in name:
        return "Code"
    if "n8n" in name:
        return "n8n"
    return "unknown"


def register_session_client(session_id: str, raw_client_name: Optional[str]) -> None:
    """Legacy: remember client type for an echoed correlation id after initialize."""
    _session_clients[session_id] = _classify_client(raw_client_name)
    _session_clients.move_to_end(session_id)
    while len(_session_clients) > _SESSION_CLIENTS_MAX:
        _session_clients.popitem(last=False)


def resolve_client(session_id: str) -> str:
    client = _session_clients.get(session_id)
    if client is None:
        return "unknown"
    _session_clients.move_to_end(session_id)
    return client


def classify_client_from_info(raw_client_name: Optional[str]) -> str:
    """Classify a client from _meta / initialize clientInfo.name."""
    return _classify_client(raw_client_name)


def resolve_correlation_id(
    *,
    incoming_session_id: Optional[str],
    identity: str,
    method: str,
    is_modern: bool,
) -> str:
    """Pick a correlation id for this request.

    Modern (2026-07-28) path: use echoed header if present, else a fresh UUID
    (no identity time-bucket — that only existed for legacy session affinity).
    Legacy path: mint on initialize, else echo or fall back to time-bucket.
    """
    if incoming_session_id:
        return incoming_session_id
    if is_modern:
        return str(uuid.uuid4())
    if method == "initialize":
        return str(uuid.uuid4())
    return fallback_session_id(identity)


def fallback_session_id(identity: str) -> str:
    """Time-window correlation for legacy clients that don't echo Mcp-Session-Id.

    Identity is hashed, not embedded: the id may appear in response headers
    and observability.db. Auth identities can include non-latin-1 characters.
    """
    bucket = int(time.time() // SESSION_FALLBACK_WINDOW_SECONDS)
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return f"noid:{digest}:{bucket}"


def _redact(args: Any) -> Any:
    if not isinstance(args, dict):
        return args if not REDACT_ARGS else type(args).__name__
    if not REDACT_ARGS:
        return args
    return {k: type(v).__name__ for k, v in args.items()}


def log_tool_call(
    *,
    session_id: str,
    client: str,
    tool_name: str,
    args: Any,
    status: str,
    error: Optional[str],
    latency_ms: int,
    response_bytes: int,
) -> None:
    """Enqueue a tool-call record. Never raises."""
    try:
        record = {
            "session_id": session_id,
            "client": client,
            "tool_name": tool_name,
            "args": json.dumps(_redact(args), default=str),
            "status": status,
            "error": error,
            "latency_ms": latency_ms,
            "response_bytes": response_bytes,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        _queue.put_nowait(record)
    except asyncio.QueueFull:
        global _dropped_count
        _dropped_count += 1
    except Exception:
        pass


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS tool_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            client TEXT,
            tool_name TEXT,
            args TEXT,
            status TEXT,
            error TEXT,
            latency_ms INTEGER,
            response_bytes INTEGER,
            ts TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_tool_calls_session ON tool_calls(session_id);
        CREATE INDEX IF NOT EXISTS idx_tool_calls_ts ON tool_calls(ts);
        CREATE TABLE IF NOT EXISTS session_reviews (
            session_id TEXT PRIMARY KEY,
            human_verdict TEXT,
            human_note TEXT,
            judge_verdict TEXT,
            judge_issues TEXT,
            judge_suggested_tool TEXT,
            reviewed_at TEXT
        );
        """
    )
    conn.commit()


def _write_batch(records: List[Dict[str, Any]]) -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        _init_schema(conn)
        conn.executemany(
            """INSERT INTO tool_calls
               (session_id, client, tool_name, args, status, error, latency_ms, response_bytes, ts)
               VALUES (:session_id, :client, :tool_name, :args, :status, :error, :latency_ms, :response_bytes, :ts)""",
            records,
        )
        conn.commit()
    finally:
        conn.close()


async def init_observability() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        _init_schema(conn)
    finally:
        conn.close()


async def run_background_writer() -> None:
    """Drains the queue and flushes to SQLite off the request path."""
    loop = asyncio.get_running_loop()
    while True:
        try:
            record = await _queue.get()
            batch = [record]
            while len(batch) < _BATCH_MAX:
                try:
                    batch.append(_queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
            await loop.run_in_executor(None, _write_batch, batch)
        except Exception:
            await asyncio.sleep(1)
