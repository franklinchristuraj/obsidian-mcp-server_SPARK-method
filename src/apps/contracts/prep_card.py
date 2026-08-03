"""Pydantic contracts for Prep Card."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class PrepEntity(BaseModel):
    name: str
    path: str
    entity_type: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)
    agent_context: Optional[str] = None
    org_id: Optional[str] = None


class PrepResolution(BaseModel):
    matched: bool
    confidence: Literal["exact", "fuzzy", "none"] = "none"
    query: str
    message: Optional[str] = None


class PrepStaleness(BaseModel):
    last_touch: Optional[str] = None
    days_ago: Optional[int] = None
    band: Optional[Literal["fresh", "aging", "stale"]] = None
    note_path: Optional[str] = None
    note_title: Optional[str] = None


class PrepOpenQuestion(BaseModel):
    text: str
    source_note: Optional[str] = None


class PrepCommitment(BaseModel):
    text: str
    due: Optional[str] = None
    overdue: bool = False
    source_note: Optional[str] = None


class PrepConnection(BaseModel):
    name: str
    entity_type: Optional[str] = None
    edge: Optional[str] = None
    path: Optional[str] = None


class PrepRecent(BaseModel):
    date: Optional[str] = None
    title: str
    type: Optional[str] = None
    path: Optional[str] = None


class PrepCardPayload(BaseModel):
    entity: PrepEntity
    resolution: PrepResolution
    staleness: PrepStaleness
    open_questions: List[PrepOpenQuestion] = Field(default_factory=list)
    commitments: List[PrepCommitment] = Field(default_factory=list)
    connections: List[PrepConnection] = Field(default_factory=list)
    recent: List[PrepRecent] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)
    scope: str = "work"
