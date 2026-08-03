"""Lint Queue contracts."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class LintHealth(BaseModel):
    notes: int = 0
    entities: int = 0
    edges: int = 0
    orphan_entities: int = 0
    broken_links: int = 0
    alias_collisions: int = 0


class ProposedFix(BaseModel):
    kind: str
    before: str
    after: str


class LintFinding(BaseModel):
    id: str
    category: str
    severity: Literal["high", "medium", "low"] = "medium"
    note_path: str
    detail: str
    auto_fixable: bool = False
    proposed_fix: Optional[ProposedFix] = None


class LintQueuePayload(BaseModel):
    scope: str
    health: LintHealth
    findings: List[LintFinding] = Field(default_factory=list)


class LintApplyResult(BaseModel):
    applied: List[str] = Field(default_factory=list)
    skipped: List[Dict[str, Any]] = Field(default_factory=list)
    stale: List[str] = Field(default_factory=list)
