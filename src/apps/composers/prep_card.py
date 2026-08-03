"""Prep Card composer: fan-out to existing vault tools, no UI logic."""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.apps.composers import call_vault, require_scope
from src.apps.contracts.prep_card import (
    PrepCardPayload,
    PrepCommitment,
    PrepConnection,
    PrepEntity,
    PrepOpenQuestion,
    PrepRecent,
    PrepResolution,
    PrepStaleness,
)
from src.tools.obsidian_tools import obsidian_tools

_DUE_RE = re.compile(
    r"(?P<text>.+?)\[due::\s*(?P<due>\d{4}-\d{2}-\d{2})\s*\]",
    re.IGNORECASE,
)
_OPEN_Q_LINE = re.compile(r"^[-*]\s+\[.\]\s*(.+)$|^[-*]\s+(.+)$")


def staleness_band(days_ago: Optional[int]) -> Optional[str]:
    if days_ago is None:
        return None
    if days_ago < 14:
        return "fresh"
    if days_ago <= 45:
        return "aging"
    return "stale"


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _days_ago(d: Optional[date], today: Optional[date] = None) -> Optional[int]:
    if d is None:
        return None
    today = today or date.today()
    return (today - d).days


def _parse_open_questions(raw: Any, source_note: str) -> List[PrepOpenQuestion]:
    if not raw:
        return []
    if isinstance(raw, list):
        out = []
        for item in raw:
            if isinstance(item, dict):
                text = str(item.get("text") or item.get("question") or "").strip()
                if text:
                    out.append(
                        PrepOpenQuestion(
                            text=text, source_note=item.get("source_note") or source_note
                        )
                    )
            else:
                text = str(item).strip()
                if text:
                    out.append(PrepOpenQuestion(text=text, source_note=source_note))
        return out
    text = str(raw).strip()
    questions: List[PrepOpenQuestion] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _OPEN_Q_LINE.match(line)
        body = (m.group(1) or m.group(2) if m else line).strip()
        if body:
            questions.append(PrepOpenQuestion(text=body, source_note=source_note))
    return questions


async def _find_commitments(
    entity_path: str, entity_name: str, scope: str
) -> List[PrepCommitment]:
    """Scan notes that link the entity for [due:: YYYY-MM-DD] tasks."""
    from src.tools.obsidian_tools import obsidian_tools

    intel = obsidian_tools._get_vault_intel()
    notes = await intel._all_notes(scope, include_sections=True)
    today = date.today()
    commitments: List[PrepCommitment] = []
    entity_stem = Path(entity_path).stem.lower()
    name_l = entity_name.lower()

    for note in notes:
        if note.path == entity_path:
            continue
        body = note.body or ""
        # Prefer notes that mention the entity
        if entity_stem not in body.lower() and name_l not in body.lower():
            # still check outlinks
            linked = any(
                entity_stem in (link or "").lower() or name_l in (link or "").lower()
                for link in (note.outlinks or [])
            )
            if not linked:
                continue
        for m in _DUE_RE.finditer(body):
            due = m.group("due")
            text = m.group("text").strip(" -\t*")
            due_d = _parse_date(due)
            overdue = bool(due_d and due_d < today)
            commitments.append(
                PrepCommitment(
                    text=text[:200],
                    due=due,
                    overdue=overdue,
                    source_note=note.path,
                )
            )
    commitments.sort(key=lambda c: c.due or "9999")
    return commitments[:20]


async def compose_prep_card(
    entity: str, scope: str = "work", since: Optional[str] = None
) -> Dict[str, Any]:
    scope = require_scope(scope)
    resolved = await call_vault("resolve_entity", name=entity, scope=scope)

    if resolved.get("disambiguation_required"):
        candidates = resolved.get("candidates") or []
        return PrepCardPayload(
            entity=PrepEntity(name=entity, path=""),
            resolution=PrepResolution(
                matched=False,
                confidence="none",
                query=entity,
                message=f"Ambiguous: {len(candidates)} candidates",
            ),
            staleness=PrepStaleness(),
            gaps=["ambiguous entity — pick a candidate"],
            scope=scope,
        ).model_dump()

    canonical = resolved.get("canonical_path") or resolved.get("path") or ""
    display = (
        resolved.get("display_name")
        or resolved.get("name")
        or Path(canonical).stem.replace("-", " ").title()
    )
    fm = resolved.get("key_frontmatter") or resolved.get("frontmatter") or {}
    entity_type = resolved.get("entity_type") or fm.get("entity_type")
    agent_context = resolved.get("agent_context") or fm.get("agent_context")
    org_id = fm.get("org_id") or resolved.get("org_id")
    # org_id is often present on the entity card but outside key_frontmatter.
    if not org_id and canonical:
        try:
            intel = obsidian_tools._get_vault_intel()
            note = intel.corpus.get_note(scope, canonical)
            if note and note.frontmatter:
                org_id = note.frontmatter.get("org_id")
        except Exception:
            pass
    aliases_raw = resolved.get("aliases") or []
    if isinstance(aliases_raw, str):
        aliases = [aliases_raw]
    else:
        aliases = list(aliases_raw)

    # Fuzzy vs exact: if query normalized differs from display/aliases
    q_norm = entity.strip().lower()
    alias_norms = {a.strip().lower() for a in aliases}
    alias_norms.add(display.strip().lower())
    alias_norms.add(Path(canonical).stem.replace("-", " ").lower())
    confidence = "exact" if q_norm in alias_norms or q_norm == Path(canonical).stem.lower() else "fuzzy"
    resolution_msg = None
    if confidence == "fuzzy":
        resolution_msg = f"matched {entity!r} to {display}"

    dossier = await call_vault("get_dossier", name=display, scope=scope, since=since)
    if dossier.get("disambiguation_required"):
        dossier = resolved

    last = await call_vault("last_touch", name=display, scope=scope)
    timeline = await call_vault("timeline", name=display, scope=scope)

    touch = last.get("last_touch") or {}
    touch_date = _parse_date(touch.get("date") if isinstance(touch, dict) else None)
    days = _days_ago(touch_date)
    band = staleness_band(days)

    open_q_raw = dossier.get("open_questions") or ""
    open_questions = _parse_open_questions(open_q_raw, canonical)

    connections: List[PrepConnection] = []
    for c in (dossier.get("connections") or resolved.get("connections") or [])[:12]:
        if isinstance(c, dict):
            connections.append(
                PrepConnection(
                    name=c.get("display") or c.get("name") or c.get("link") or "",
                    entity_type=c.get("entity_type"),
                    edge=c.get("edge") or c.get("relation"),
                    path=c.get("path"),
                )
            )

    recent: List[PrepRecent] = []
    for item in (timeline.get("items") or [])[:5]:
        if not isinstance(item, dict):
            continue
        recent.append(
            PrepRecent(
                date=item.get("date"),
                title=item.get("summary") or item.get("title") or item.get("path") or "",
                type=item.get("type"),
                path=item.get("path"),
            )
        )

    commitments = await _find_commitments(canonical, display, scope)

    gaps: List[str] = []
    if not org_id and entity_type == "customer":
        gaps.append("no org_id set")
    if band == "stale":
        gaps.append(f"stale entity ({days} days since last touch)")
    if not recent:
        gaps.append("no recent interactions on timeline")
    # Check last engagement debrief heuristically
    engagements = [
        r for r in recent if r.type in ("engagement", "event") and r.path
    ]
    if engagements:
        last_eng = engagements[0]
        try:
            note = await call_vault("read_note", path=last_eng.path, scope=scope)
            body = ""
            if isinstance(note, dict):
                body = note.get("content") or note.get("text") or ""
                if isinstance(body, dict):
                    body = body.get("content") or ""
            if "debrief" in (last_eng.path or "").lower() or "## High-signal debrief" in str(body):
                pass
            elif last_eng.type == "engagement" and "High-signal debrief" not in str(body):
                gaps.append("last engagement has no debrief")
        except Exception:
            pass

    payload = PrepCardPayload(
        entity=PrepEntity(
            name=display,
            path=canonical,
            entity_type=entity_type,
            aliases=aliases,
            agent_context=agent_context,
            org_id=org_id,
        ),
        resolution=PrepResolution(
            matched=True,
            confidence=confidence,  # type: ignore[arg-type]
            query=entity,
            message=resolution_msg,
        ),
        staleness=PrepStaleness(
            last_touch=touch.get("date") if isinstance(touch, dict) else None,
            days_ago=days,
            band=band,  # type: ignore[arg-type]
            note_path=touch.get("path") if isinstance(touch, dict) else None,
            note_title=touch.get("summary") if isinstance(touch, dict) else None,
        ),
        open_questions=open_questions,
        commitments=commitments,
        connections=connections,
        recent=recent,
        gaps=gaps,
        scope=scope,
    )
    return payload.model_dump()


async def compose_prep_card_expand(
    entity: str,
    scope: str = "work",
    hops: int = 1,
    token_budget: int = 4000,
) -> Dict[str, Any]:
    scope = require_scope(scope)
    return await call_vault(
        "build_context",
        seed=entity,
        scope=scope,
        depth=hops,
        token_budget=token_budget,
    )


async def compose_prep_card_timeline(
    entity: str,
    scope: str = "work",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> Dict[str, Any]:
    scope = require_scope(scope)
    return await call_vault(
        "timeline",
        name=entity,
        scope=scope,
        start=from_date,
        end=to_date,
    )
