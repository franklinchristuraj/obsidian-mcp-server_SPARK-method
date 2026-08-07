"""
In-process tool-call observability (Ziksaka).

Logs every tools/call to a local SQLite file so tool-selection behavior
(redundant calls, wrong tool, dead tools) can be reviewed after the fact.
Writes never happen on the request path: log_tool_call() only enqueues,
a background task drains the queue and flushes to SQLite.

Session correlation: the MCP wire protocol doesn't expose a native
session id here (no StreamableHTTP session handling in this server), so
main.py mints an Mcp-Session-Id on `initialize` and expects the client to
echo it back per the Streamable HTTP spec. Clients that don't echo it
fall back to a coarse time-window bucket keyed by API-key identity.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
import time
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

# session_id -> classified client ("Desktop" | "Code" | "n8n" | "unknown"),
# populated from clientInfo.name on `initialize`. Bounded and LRU-evicted:
# every `initialize` mints a new id, so an unbounded dict grows for the life
# of the process and lets any authenticated client exhaust memory by
# reconnecting in a loop.
_SESSION_CLIENTS_MAX = 10_000
_session_clients: "OrderedDict[str, str]" = OrderedDict()


@dataclass(frozen=True)
class CallContext:
    session_id: str
    client: str


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
    _session_clients[session_id] = _classify_client(raw_client_name)
    _session_clients.move_to_end(session_id)
    while len(_session_clients) > _SESSION_CLIENTS_MAX:
        _session_clients.popitem(last=False)


def resolve_client(session_id: str) -> str:
    client = _session_clients.get(session_id)
    if client is None:
        return "unknown"
    # Touch on read so a long-running conversation isn't evicted by a burst
    # of short-lived ones.
    _session_clients.move_to_end(session_id)
    return client


def fallback_session_id(identity: str) -> str:
    """Time-window correlation for clients that don't echo Mcp-Session-Id.

    Materially worse than a real session id (PRD §6) — over-call detection
    degrades since concurrent/overlapping conversations from the same key
    collapse into one bucket.

    Identity is hashed, not embedded: the fallback id is returned in the
    Mcp-Session-Id response header (and thus nginx access logs) and written
    to observability.db. Auth identities include truncated API-key prefixes
    and a U+2026 ellipsis that is not latin-1 encodable for HTTP headers.
    """
    bucket = int(time.time() // SESSION_FALLBACK_WINDOW_SECONDS)
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return f"noid:{digest}:{bucket}"


def _redact(args: Any) -> Any:
    # `arguments` is client-supplied and need not be an object. Record the
    # shape of a malformed one rather than raising, which would drop the
    # record for exactly the misbehaving call worth keeping.
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
    """Enqueue a tool-call record. Never raises — a logging failure must
    never break the tool call it's observing (PRD §4)."""
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
        # CREATE TABLE IF NOT EXISTS is cheap and idempotent — guards
        # against the DB file disappearing after startup (rotation,
        # accidental delete, disk restore) leaving the writer stuck
        # failing every batch with no way to recover without a restart.
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
    """Drains the queue and flushes to SQLite off the request path.

    A write failure here (e.g. disk full) must not take down the process
    or block new tool calls from being enqueued — log and keep going.
    """
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
