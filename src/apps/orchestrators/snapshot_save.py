"""Snapshot save orchestrator."""
from __future__ import annotations

from typing import Any, Dict, List

from src.apps.composers import call_vault, require_scope


async def save_snapshots(
    rows: List[Dict[str, Any]], scope: str = "work"
) -> Dict[str, Any]:
    scope = require_scope(scope, allowed=("work",))
    if not rows:
        raise ValueError("rows must be non-empty")

    results: List[Dict[str, Any]] = []
    for i, row in enumerate(rows):
        org_id = row.get("org_id")
        date_str = row.get("date")
        metrics = row.get("metrics") or {}
        source = row.get("source") or "c360"
        mode = row.get("mode")
        if not org_id or not date_str:
            results.append({"index": i, "ok": False, "error": "org_id and date required"})
            continue
        if mode not in ("live", "reconstructed"):
            results.append(
                {
                    "index": i,
                    "ok": False,
                    "error": "mode must be explicitly live or reconstructed",
                }
            )
            continue
        try:
            payload = await call_vault(
                "capture_snapshot",
                org_id=org_id,
                date=date_str,
                metrics=metrics,
                source=source,
                mode=mode,
                scope=scope,
            )
            results.append(
                {
                    "index": i,
                    "ok": True,
                    "operation": payload.get("operation"),
                    "org_id": org_id,
                    "date": date_str,
                }
            )
        except Exception as e:
            results.append({"index": i, "ok": False, "error": str(e)})

    return {"results": results, "scope": scope}
