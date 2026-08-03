"""Debrief Form contracts."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DebriefCustomer(BaseModel):
    query: Optional[str] = None
    resolved: bool = False
    candidates: List[Dict[str, Any]] = Field(default_factory=list)
    path: Optional[str] = None
    org_id: Optional[str] = None


class EntityGap(BaseModel):
    name: str
    entity_type: str
    exists: bool
    will_create: bool = True
    employer: Optional[str] = None
    collision: Optional[str] = None


class ParentEngagement(BaseModel):
    path: str
    title: str
    engagement_type: Optional[str] = None
    trial_end: Optional[str] = None


class SignalVocab(BaseModel):
    id: str
    label: str


class DebriefVocab(BaseModel):
    event_types: List[str] = Field(default_factory=list)
    touchpoint_types: List[str] = Field(default_factory=list)
    engagement_types: List[str] = Field(default_factory=list)
    signals: List[SignalVocab] = Field(default_factory=list)


class DebriefFormPayload(BaseModel):
    date: str
    customer: DebriefCustomer
    entity_gaps: List[EntityGap] = Field(default_factory=list)
    parent_engagements: List[ParentEngagement] = Field(default_factory=list)
    vocab: DebriefVocab = Field(default_factory=DebriefVocab)
    ontology_version: str = "v1"
    scope: str = "work"
