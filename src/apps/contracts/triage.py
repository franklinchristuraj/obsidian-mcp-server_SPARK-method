"""Triage Board contracts."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class TriageCounts(BaseModel):
    thought: int = 0
    post: int = 0
    excerpt: int = 0
    total: int = 0


class TriageItem(BaseModel):
    path: str
    title: str
    capture_type: Optional[str] = None
    spark: Optional[str] = None
    source: Optional[str] = None
    captured: Optional[str] = None
    age_days: Optional[int] = None
    excerpt: Optional[str] = None
    suggested_scope: Optional[str] = None
    gaps: List[str] = Field(default_factory=list)


class TriageBoardPayload(BaseModel):
    counts: TriageCounts
    oldest_days: Optional[int] = None
    items: List[TriageItem] = Field(default_factory=list)
    scopes: List[str] = Field(default_factory=lambda: ["personal", "passion", "work"])
    target_types: List[str] = Field(
        default_factory=lambda: ["seed", "resource", "knowledge"]
    )
