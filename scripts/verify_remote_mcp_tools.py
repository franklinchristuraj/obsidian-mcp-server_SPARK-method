#!/usr/bin/env python3
"""Verify all MCP tools over HTTPS remote endpoint."""
import json
import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE = os.getenv("MCP_BASE_URL", "https://mcp.ziksaka.com").rstrip("/")
MCP = f"{BASE}/mcp"
API_KEY = os.getenv("MCP_API_KEY", "")

READ_ONLY_CALLS = [
    ("ping", {}),
    ("workspaces", {}),
    ("vault_structure", {"use_cache": True}),
    ("list_notes", {"scope": "personal", "limit": 2}),
    ("list_journal", {
        "startDate": "2026-05-01",
        "endDate": "2026-05-31",
        "scope": "personal",
    }),
    ("search", {"keyword": "daily", "scope": "personal", "limit": 2}),
    ("note_exists", {"path": "06_daily-notes/2026-05-28.md", "scope": "personal"}),
    ("read_note", {"path": "06_daily-notes/2026-05-28.md", "scope": "personal"}),
]


def mcp_call(method: str, params: dict | None = None, req_id: int = 1) -> dict:
    body = {"jsonrpc": "2.0", "method": method, "id": req_id}
    if params is not None:
        body["params"] = params
    r = httpx.post(
        MCP,
        json=body,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        timeout=60.0,
    )
    r.raise_for_status()
    return r.json()


def tool_call(name: str, arguments: dict, req_id: int) -> tuple[bool, str]:
    out = mcp_call(
        "tools/call",
        {"name": name, "arguments": arguments},
        req_id=req_id,
    )
    if "error" in out:
        return False, json.dumps(out["error"])
    content = out.get("result", {}).get("content", [])
    text = content[0].get("text", "") if content else str(out)
    if text.startswith("❌") or "failed:" in text.lower()[:80]:
        return False, text[:200].replace("\n", " ")
    preview = text[:120].replace("\n", " ")
    return True, preview


def main() -> int:
    print(f"Remote MCP: {MCP}")
    if not API_KEY:
        print("MCP_API_KEY not set", file=sys.stderr)
        return 1

    ok = True

    # tools/list
    listed = mcp_call("tools/list", req_id=0)
    if "error" in listed:
        print(f"FAIL tools/list: {listed['error']}")
        return 1
    names = sorted(t["name"] for t in listed["result"]["tools"])
    print(f"tools/list: {len(names)} tools — {', '.join(names)}")

    expected = {
        "ping",
        "workspaces",
        "vault_structure",
        "list_notes",
        "list_journal",
        "search",
        "read_note",
        "create_note",
        "update_note",
        "append_note",
        "note_exists",
        "delete_note",
    }
    missing = expected - set(names)
    extra = set(names) - expected
    if missing:
        print(f"  MISSING: {sorted(missing)}")
        ok = False
    if extra:
        print(f"  EXTRA: {sorted(extra)}")
    else:
        print("  All expected tool names present")

    for i, (name, args) in enumerate(READ_ONLY_CALLS, start=1):
        try:
            passed, preview = tool_call(name, args, req_id=i)
            status = "OK" if passed else "FAIL"
            print(f"  [{status}] {name}: {preview}...")
            if not passed:
                ok = False
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
            ok = False

  # Write tools skipped on remote (avoid vault mutation)
    skipped = ["create_note", "update_note", "append_note", "delete_note"]
    print(f"  [SKIP] {', '.join(skipped)} (mutating; not run against production)")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
