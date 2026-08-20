#!/usr/bin/env python3
"""
Observability Report for Obsidian MCP Server
Summarizes tool_calls / protocol_calls from observability.db for quick
after-the-fact review (error rates, latency, client mix, recent failures).
"""
import argparse
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

DB_PATH = os.getenv("OBS_DB_PATH", "observability.db")


def connect(db_path: str) -> sqlite3.Connection:
    if not os.path.exists(db_path):
        print(f"❌ No observability DB at {db_path}")
        sys.exit(1)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def since_ts(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def print_overview(conn: sqlite3.Connection, cutoff: str) -> None:
    tc = conn.execute("SELECT COUNT(*) FROM tool_calls WHERE ts >= ?", (cutoff,)).fetchone()[0]
    pc = conn.execute("SELECT COUNT(*) FROM protocol_calls WHERE ts >= ?", (cutoff,)).fetchone()[0]
    sessions = conn.execute(
        "SELECT COUNT(DISTINCT session_id) FROM tool_calls WHERE ts >= ?", (cutoff,)
    ).fetchone()[0]
    lo, hi = conn.execute(
        "SELECT MIN(ts), MAX(ts) FROM tool_calls WHERE ts >= ?", (cutoff,)
    ).fetchone()
    unknown = conn.execute(
        "SELECT COUNT(*) FROM tool_calls WHERE ts >= ? AND client='unknown'", (cutoff,)
    ).fetchone()[0]

    print("=== Overview ===")
    print(f"tool_calls:      {tc}")
    print(f"protocol_calls:  {pc}")
    print(f"distinct sessions: {sessions}")
    print(f"date range:      {lo} .. {hi}")
    if tc:
        print(f"client=unknown:  {unknown} ({100 * unknown / tc:.0f}%)")
    print()


def print_tool_breakdown(conn: sqlite3.Connection, cutoff: str) -> None:
    print("=== Tool calls (name, count, errors, error%, avg ms, max ms) ===")
    rows = conn.execute(
        """
        SELECT tool_name,
               COUNT(*) AS n,
               SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) AS errors,
               AVG(latency_ms) AS avg_ms,
               MAX(latency_ms) AS max_ms
        FROM tool_calls
        WHERE ts >= ?
        GROUP BY tool_name
        ORDER BY n DESC
        """,
        (cutoff,),
    ).fetchall()
    for r in rows:
        err_pct = 100 * r["errors"] / r["n"] if r["n"] else 0
        print(
            f"  {r['tool_name']:<20} n={r['n']:<5} errors={r['errors']:<4} "
            f"({err_pct:4.0f}%)  avg={r['avg_ms'] or 0:6.1f}ms  max={r['max_ms'] or 0}ms"
        )
    print()


def print_client_breakdown(conn: sqlite3.Connection, cutoff: str) -> None:
    print("=== Clients ===")
    rows = conn.execute(
        "SELECT client, COUNT(*) n FROM tool_calls WHERE ts >= ? GROUP BY client ORDER BY n DESC",
        (cutoff,),
    ).fetchall()
    for r in rows:
        print(f"  {r['client']:<12} {r['n']}")
    print()


def print_protocol_breakdown(conn: sqlite3.Connection, cutoff: str) -> None:
    print("=== Protocol calls (method, count, errors) ===")
    rows = conn.execute(
        """
        SELECT method, COUNT(*) n, SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) errors
        FROM protocol_calls
        WHERE ts >= ?
        GROUP BY method
        ORDER BY n DESC
        """,
        (cutoff,),
    ).fetchall()
    for r in rows:
        print(f"  {r['method']:<16} n={r['n']:<5} errors={r['errors']}")
    print()


def print_recent_errors(conn: sqlite3.Connection, cutoff: str, limit: int) -> None:
    print(f"=== Recent tool errors (last {limit}) ===")
    rows = conn.execute(
        """
        SELECT ts, session_id, client, tool_name, args, error
        FROM tool_calls
        WHERE ts >= ? AND status='error'
        ORDER BY id DESC
        LIMIT ?
        """,
        (cutoff, limit),
    ).fetchall()
    if not rows:
        print("  (none)")
    for r in rows:
        print(f"  [{r['ts']}] {r['tool_name']}({r['args']}) client={r['client']}")
        print(f"      {r['error']}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DB_PATH, help="Path to observability.db")
    parser.add_argument("--days", type=int, default=30, help="Look back N days (default 30)")
    parser.add_argument("--errors", type=int, default=10, help="Number of recent errors to show")
    args = parser.parse_args()

    conn = connect(args.db)
    cutoff = since_ts(args.days)
    try:
        print_overview(conn, cutoff)
        print_tool_breakdown(conn, cutoff)
        print_client_breakdown(conn, cutoff)
        print_protocol_breakdown(conn, cutoff)
        print_recent_errors(conn, cutoff, args.errors)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
