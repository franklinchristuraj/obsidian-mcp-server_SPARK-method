"""Debrief preview + submit orchestrators."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from src.apps.composers import call_vault, require_scope

# In-memory idempotency for process lifetime (vault also checked via note_exists).
_IDEMPOTENCY: Dict[str, Dict[str, Any]] = {}


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:48] or "note"


def _plan_writes(payload: Dict[str, Any], scope: str) -> List[Dict[str, str]]:
    day = payload.get("date") or ""
    customer = (payload.get("customer") or {}).get("query") or payload.get("customer_name") or "unknown"
    slug = _slug(f"{customer}-{(payload.get('event_type') or 'meeting')}")
    writes: List[Dict[str, str]] = []

    for gap in payload.get("entity_gaps") or []:
        if gap.get("will_create") and not gap.get("exists"):
            et = gap.get("entity_type") or "person"
            name = gap.get("name") or ""
            path = f"entities/{et}/{_slug(name)}.md"
            writes.append({"op": "create_note", "path": path, "kind": "entity"})

    if payload.get("create_event", True):
        writes.append(
            {
                "op": "create_event",
                "path": f"entities/event/{day}_{slug}.md",
                "kind": "event",
            }
        )
    if payload.get("create_engagement"):
        writes.append(
            {
                "op": "create_engagement",
                "path": f"12_engagements/{day}_{_slug(customer)}.md",
                "kind": "engagement",
            }
        )
    writes.append(
        {
            "op": "create_note",
            "path": f"11_meeting-notes/{day}_{slug}.md",
            "kind": "meeting",
        }
    )
    writes.append({"op": "update", "path": "index.md", "kind": "index"})
    writes.append({"op": "update", "path": "log.md", "kind": "log"})
    return writes


async def preview_debrief(payload: Dict[str, Any], scope: str = "work") -> Dict[str, Any]:
    scope = require_scope(scope, allowed=("work",))
    writes = _plan_writes(payload, scope)
    backlinks = []
    customer = (payload.get("customer") or {}).get("query")
    if customer:
        backlinks.append(f"{_slug(customer)} ↔ event")
    for gap in payload.get("entity_gaps") or []:
        if gap.get("entity_type") == "person" and gap.get("employer"):
            backlinks.append(f"{_slug(gap['name'])} → {_slug(gap['employer'])}")
    return {
        "writes": writes,
        "write_count": len(writes),
        "backlinks": backlinks,
        "scope": scope,
    }


async def submit_debrief(
    payload: Dict[str, Any],
    idempotency_key: str,
    scope: str = "work",
) -> Dict[str, Any]:
    scope = require_scope(scope, allowed=("work",))
    if not idempotency_key:
        raise ValueError("idempotency_key is required")

    if idempotency_key in _IDEMPOTENCY:
        cached = dict(_IDEMPOTENCY[idempotency_key])
        cached["idempotent_replay"] = True
        return cached

    plan = await preview_debrief(payload, scope=scope)
    written: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []

    create_entities = payload.get("create_missing_entities", True)
    day = payload.get("date") or ""
    customer = (payload.get("customer") or {}).get("query") or ""
    attendees = payload.get("attendees") or []

    # 1. Entity cards first
    if create_entities:
        for gap in payload.get("entity_gaps") or []:
            if gap.get("exists") or not gap.get("will_create", True):
                continue
            et = gap.get("entity_type") or "person"
            name = gap.get("name") or ""
            path = f"entities/{et}/{_slug(name)}.md"
            body = (
                f"---\n"
                f"type: entity\n"
                f"entity_type: {et}\n"
                f"created: {day}\n"
                f'agent_context: "Created via debrief_submit"\n'
                f"tags: []\n"
                f"---\n\n"
                f"# {name}\n\n"
                f"## Connections\n\n"
            )
            if gap.get("employer"):
                body += f"- Employer: [[{_slug(gap['employer'])}]]\n"
            try:
                await call_vault(
                    "create_note",
                    path=path,
                    content=body,
                    scope=scope,
                    create_folders=True,
                )
                written.append({"op": "create_note", "path": path, "ok": True})
            except Exception as e:
                failed.append({"op": "create_note", "path": path, "error": str(e)})
                # Continue — partial failure reported honestly

    # 2. create_event
    if payload.get("create_event", True) and not any(
        f.get("op") == "create_note" and f.get("error") for f in failed if False
    ):
        try:
            result = await call_vault(
                "create_event",
                event_type=payload.get("event_type") or "other",
                event_date=day,
                customer=customer or None,
                participants=attendees if isinstance(attendees, list) else [],
                parent_engagement=payload.get("parent_engagement") or "",
                touchpoint_type=payload.get("touchpoint_type") or "",
                scope=scope,
            )
            path = (result.get("path") or result.get("event_path") or "")
            written.append({"op": "create_event", "path": path, "ok": True})
        except Exception as e:
            failed.append({"op": "create_event", "error": str(e)})

    # 3. optional engagement
    if payload.get("create_engagement"):
        try:
            result = await call_vault(
                "create_engagement",
                engagement_type=payload.get("engagement_type") or "demo",
                customer=customer,
                date=day,
                scope=scope,
            )
            written.append(
                {
                    "op": "create_engagement",
                    "path": result.get("path") or "",
                    "ok": True,
                }
            )
        except Exception as e:
            failed.append({"op": "create_engagement", "error": str(e)})

    # 4. meeting note
    slug = _slug(f"{customer}-{(payload.get('event_type') or 'meeting')}")
    meeting_path = f"11_meeting-notes/{day}_{slug}.md"
    meeting_body = (
        f"---\ntype: meeting\ndate: {day}\ncustomer: {customer}\n---\n\n"
        f"# {customer} — {payload.get('event_type') or 'meeting'}\n\n"
        f"## What happened\n\n{payload.get('what_happened') or ''}\n\n"
        f"## Decisions\n\n{payload.get('decisions') or ''}\n\n"
        f"## Open questions\n\n{payload.get('open_questions') or ''}\n"
    )
    try:
        await call_vault(
            "create_note",
            path=meeting_path,
            content=meeting_body,
            scope=scope,
            create_folders=True,
        )
        written.append({"op": "create_note", "path": meeting_path, "ok": True})
    except Exception as e:
        failed.append({"op": "create_note", "path": meeting_path, "error": str(e)})

    # 5. index.md / log.md append (best-effort)
    for path, line in (
        ("index.md", f"- [[{meeting_path}]] debrief {day}"),
        ("log.md", f"- {day}: debrief {customer} → [[{meeting_path}]]"),
    ):
        try:
            await call_vault(
                "append_note",
                path=path,
                content=line,
                scope=scope,
            )
            written.append({"op": "update", "path": path, "ok": True})
        except Exception as e:
            failed.append({"op": "update", "path": path, "error": str(e)})

    result = {
        "written": written,
        "failed": failed,
        "plan": plan,
        "idempotency_key": idempotency_key,
        "partial": bool(failed) and bool(written),
        "scope": scope,
    }
    if not failed:
        _IDEMPOTENCY[idempotency_key] = result
    return result
