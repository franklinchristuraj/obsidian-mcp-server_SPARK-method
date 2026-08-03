"""Snapshot grid composer (work scope only)."""
from __future__ import annotations

import asyncio
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.apps.composers import require_scope
from src.apps.contracts.snapshot import (
    SnapshotBlocked,
    SnapshotEngagement,
    SnapshotGridPayload,
    SnapshotOrg,
    SnapshotWindow,
    WindowSnapshot,
)
from src.tools.obsidian_tools import obsidian_tools
from src.vault_intelligence.tools import SNAPSHOT_MATCH_TOLERANCE_DAYS

WINDOWS = (-30, 0, 30, 90)


def _parse_iso(value: Any) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


async def compose_snapshot_grid(
    org_id: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    scope: str = "work",
) -> Dict[str, Any]:
    scope = require_scope(scope, allowed=("work",))
    intel = obsidian_tools._get_vault_intel()
    notes = await intel._all_notes(scope, folder="12_engagements", include_sections=False)

    from_d = _parse_iso(from_date)
    to_d = _parse_iso(to_date)

    blocked: List[SnapshotBlocked] = []
    by_org: Dict[str, SnapshotOrg] = {}

    for note in notes:
        if "_snapshots" in note.path.replace("\\", "/"):
            continue
        if not note.path.endswith(".md"):
            continue
        fm = note.frontmatter or {}
        eng_date = _parse_iso(fm.get("date") or fm.get("engagement_date"))
        if eng_date is None:
            stem = Path(note.path).name
            eng_date = _parse_iso(stem[:10])
        if eng_date is None:
            continue
        if from_d and eng_date < from_d:
            continue
        if to_d and eng_date > to_d:
            continue

        oid = str(fm.get("org_id") or "").strip()
        if not oid:
            blocked.append(SnapshotBlocked(path=note.path, reason="no org_id"))
            continue
        if org_id and oid != org_id:
            continue

        display = (
            str(fm.get("customer") or fm.get("title") or Path(note.path).stem)
            .strip("[]")
            .strip()
        )
        customer_status = str(fm.get("customer_status") or fm.get("status") or "").lower()
        if customer_status not in ("prospect", "existing"):
            if "prospect" in customer_status or str(fm.get("sales_stage") or "").lower() in (
                "prospect",
                "trial",
            ):
                customer_status = "prospect"
            else:
                customer_status = "existing"

        snapshots = await asyncio.to_thread(intel._load_snapshots, oid)
        windows: List[SnapshotWindow] = []
        for offset in WINDOWS:
            target = eng_date + timedelta(days=offset)
            closest = intel._closest_snapshot(snapshots, target)
            if closest is None:
                status = "missing"
                snap = None
                if snapshots:
                    any_near = min(
                        snapshots,
                        key=lambda s: abs((s["captured_date"] - target).days),
                    )
                    if (
                        abs((any_near["captured_date"] - target).days)
                        > SNAPSHOT_MATCH_TOLERANCE_DAYS
                    ):
                        status = "out_of_tolerance"
                        snap = WindowSnapshot(
                            date=any_near["date"],
                            mode=any_near.get("mode"),
                            source=any_near.get("source"),
                            metrics=any_near.get("metrics") or {},
                        )
            else:
                status = "present"
                snap = WindowSnapshot(
                    date=closest["date"],
                    mode=closest.get("mode"),
                    source=closest.get("source"),
                    metrics=closest.get("metrics") or {},
                )
            windows.append(
                SnapshotWindow(
                    offset=offset,
                    target_date=target.isoformat(),
                    status=status,  # type: ignore[arg-type]
                    snapshot=snap,
                )
            )

        org = by_org.get(oid)
        if org is None:
            org = SnapshotOrg(org_id=oid, display_name=display, engagements=[])
            by_org[oid] = org
        org.engagements.append(
            SnapshotEngagement(
                path=note.path,
                engagement_date=eng_date.isoformat(),
                engagement_type=fm.get("engagement_type"),
                customer_status=customer_status,  # type: ignore[arg-type]
                windows=windows,
            )
        )

    payload = SnapshotGridPayload(
        tolerance_days=SNAPSHOT_MATCH_TOLERANCE_DAYS,
        orgs=sorted(by_org.values(), key=lambda o: o.display_name.lower()),
        blocked=blocked,
    )
    return payload.model_dump()
