"""Snapshot Entry contracts."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class SnapshotMetrics(BaseModel):
    scenarios: Optional[int] = None
    ai_apps: Optional[int] = None
    ops_consumed: Optional[int] = None
    active_users: Optional[int] = None


class WindowSnapshot(BaseModel):
    date: Optional[str] = None
    mode: Optional[Literal["live", "reconstructed"]] = None
    source: Optional[str] = None
    metrics: Dict[str, Any] = Field(default_factory=dict)


class SnapshotWindow(BaseModel):
    offset: int
    target_date: str
    status: Literal["present", "missing", "out_of_tolerance"]
    snapshot: Optional[WindowSnapshot] = None


class SnapshotEngagement(BaseModel):
    path: str
    engagement_date: str
    engagement_type: Optional[str] = None
    customer_status: Optional[Literal["prospect", "existing"]] = None
    windows: List[SnapshotWindow] = Field(default_factory=list)


class SnapshotOrg(BaseModel):
    org_id: str
    display_name: str
    engagements: List[SnapshotEngagement] = Field(default_factory=list)


class SnapshotBlocked(BaseModel):
    path: str
    reason: str


class SnapshotGridPayload(BaseModel):
    tolerance_days: int = 14
    metric_keys: List[str] = Field(
        default_factory=lambda: ["scenarios", "ai_apps", "ops_consumed", "active_users"]
    )
    orgs: List[SnapshotOrg] = Field(default_factory=list)
    blocked: List[SnapshotBlocked] = Field(default_factory=list)
