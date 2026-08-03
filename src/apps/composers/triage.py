"""Triage board composer for root 01_seeds/ inbox."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.apps.contracts.triage import (
    TriageBoardPayload,
    TriageCounts,
    TriageItem,
)
from src.tools.obsidian_tools import obsidian_tools


def _age_days(captured: Optional[str], today: Optional[date] = None) -> Optional[int]:
    if not captured:
        return None
    today = today or date.today()
    try:
        d = date.fromisoformat(captured[:10])
        return (today - d).days
    except ValueError:
        return None


async def compose_triage_board(limit: int = 50) -> Dict[str, Any]:
    client = obsidian_tools.client
    if client is None:
        raise ValueError("Obsidian client not initialized")

    vault = Path(client.vault_path)
    seeds = vault / "01_seeds"
    items: List[TriageItem] = []
    counts = TriageCounts()

    if seeds.is_dir():
        files = sorted(seeds.glob("*.md"), key=lambda p: p.stat().st_mtime)
        for path in files:
            text = path.read_text(encoding="utf-8")
            fm: Dict[str, Any] = {}
            body = text
            if text.startswith("---"):
                parts = text.split("---", 2)
                if len(parts) >= 3:
                    import yaml

                    try:
                        fm = yaml.safe_load(parts[1]) or {}
                    except Exception:
                        fm = {}
                    body = parts[2]

            status = str(fm.get("status") or "").lower()
            note_type = str(fm.get("type") or "").lower()
            if status and status != "inbox":
                continue
            if note_type and note_type not in ("capture", ""):
                continue

            capture_type = str(fm.get("capture_type") or "thought").lower()
            if capture_type == "thought":
                counts.thought += 1
            elif capture_type == "post":
                counts.post += 1
            elif capture_type == "excerpt":
                counts.excerpt += 1

            title = str(fm.get("title") or path.stem)
            spark = str(fm.get("spark") or "").strip() or None
            captured = str(fm.get("captured") or "")
            age = _age_days(captured)
            excerpt = " ".join(body.strip().split())[:300]
            gaps: List[str] = []
            if not spark:
                gaps.append("no spark")

            rel = f"01_seeds/{path.name}"
            items.append(
                TriageItem(
                    path=rel,
                    title=title,
                    capture_type=capture_type,
                    spark=spark,
                    source=str(fm.get("source") or "") or None,
                    captured=captured or None,
                    age_days=age,
                    excerpt=excerpt or None,
                    suggested_scope=None,
                    gaps=gaps,
                )
            )

    counts.total = len(items)
    # oldest first for triage
    items.sort(key=lambda i: i.age_days if i.age_days is not None else -1, reverse=True)
    oldest = items[0].age_days if items else None
    limited = items[: max(1, min(limit, 200))]

    return TriageBoardPayload(
        counts=counts,
        oldest_days=oldest,
        items=limited,
    ).model_dump()
