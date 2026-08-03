"""Debrief form composer."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.apps.composers import call_vault, require_scope
from src.apps.contracts.debrief import (
    DebriefCustomer,
    DebriefFormPayload,
    DebriefVocab,
    EntityGap,
    ParentEngagement,
    SignalVocab,
)
from src.tools.obsidian_tools import obsidian_tools
from src.vault_intelligence.parser import EVENT_TYPES, TOUCHPOINT_TYPES, ENGAGEMENT_TYPES


def _load_vocab_from_vault(scope: str = "work") -> DebriefVocab:
    """Prefer vault ontology; fall back to parser constants."""
    event_types = sorted(EVENT_TYPES)
    touchpoint_types = sorted(TOUCHPOINT_TYPES)
    engagement_types = sorted(ENGAGEMENT_TYPES) if ENGAGEMENT_TYPES else []
    signals: List[SignalVocab] = []

    client = obsidian_tools.client
    if client is not None:
        vault = Path(client.vault_path)
        ontology = vault / scope / "00_system" / "ontology-v1.md"
        if ontology.is_file():
            text = ontology.read_text(encoding="utf-8")
            # Pull fenced enum-looking lines: `- \`foo\`` or plain bullets under headings
            for m in re.finditer(
                r"(?im)^###?\s+Event types?\s*$([\s\S]*?)(?=^###?\s|\Z)", text
            ):
                block = m.group(1)
                found = re.findall(r"`([a-z0-9_-]+)`", block)
                if found:
                    event_types = found
            for m in re.finditer(
                r"(?im)^###?\s+Engagement types?\s*$([\s\S]*?)(?=^###?\s|\Z)", text
            ):
                block = m.group(1)
                found = re.findall(r"`([a-z0-9_-]+)`", block)
                if found:
                    engagement_types = found

        signal_log = vault / scope / "00_system" / "poc-signal-log.md"
        if not signal_log.is_file():
            # alternate names
            for cand in vault.joinpath(scope, "00_system").glob("*signal*"):
                signal_log = cand
                break
        if signal_log.is_file():
            text = signal_log.read_text(encoding="utf-8")
            for m in re.finditer(
                r"(?m)^\|\s*(SIG-?\d+)\s*\|\s*([^|]+)\|", text
            ):
                signals.append(
                    SignalVocab(id=m.group(1).strip(), label=m.group(2).strip())
                )
            if not signals:
                for m in re.finditer(r"(?m)^(SIG-?\d+)\s*[:—-]\s*(.+)$", text):
                    signals.append(
                        SignalVocab(id=m.group(1).strip(), label=m.group(2).strip())
                    )

    return DebriefVocab(
        event_types=event_types,
        touchpoint_types=touchpoint_types,
        engagement_types=engagement_types or sorted(EVENT_TYPES),
        signals=signals,
    )


async def compose_debrief_form(
    customer: Optional[str] = None,
    date: Optional[str] = None,
    engagement_type: Optional[str] = None,
    scope: str = "work",
) -> Dict[str, Any]:
    scope = require_scope(scope, allowed=("work",))
    day = date or __import__("datetime").date.today().isoformat()

    cust = DebriefCustomer(query=customer, resolved=False)
    gaps: List[EntityGap] = []

    if customer:
        try:
            resolved = await call_vault("resolve_entity", name=customer, scope=scope)
            if resolved.get("disambiguation_required"):
                cust.candidates = resolved.get("candidates") or []
                cust.resolved = False
            else:
                cust.resolved = True
                cust.path = resolved.get("canonical_path")
                fm = resolved.get("frontmatter") or resolved.get("key_frontmatter") or {}
                cust.org_id = fm.get("org_id") or resolved.get("org_id")
        except Exception:
            cust.resolved = False
            gaps.append(
                EntityGap(
                    name=customer,
                    entity_type="customer",
                    exists=False,
                    will_create=True,
                )
            )

        if not cust.resolved and not gaps:
            gaps.append(
                EntityGap(
                    name=customer,
                    entity_type="customer",
                    exists=False,
                    will_create=True,
                )
            )

    parents: List[ParentEngagement] = []
    intel = obsidian_tools._get_vault_intel()
    notes = await intel._all_notes(scope, folder="12_engagements", include_sections=False)
    for note in notes:
        if "_snapshots" in note.path:
            continue
        fm = note.frontmatter or {}
        title = str(fm.get("title") or Path(note.path).stem)
        if customer:
            blob = f"{title} {fm.get('customer', '')} {note.path}".lower()
            if customer.lower() not in blob:
                continue
        parents.append(
            ParentEngagement(
                path=note.path,
                title=title,
                engagement_type=fm.get("engagement_type"),
                trial_end=str(fm.get("trial_end") or "") or None,
            )
        )
        if len(parents) >= 20:
            break

    vocab = _load_vocab_from_vault(scope)
    payload = DebriefFormPayload(
        date=day,
        customer=cust,
        entity_gaps=gaps,
        parent_engagements=parents,
        vocab=vocab,
        ontology_version="v1",
        scope=scope,
    )
    return payload.model_dump()
