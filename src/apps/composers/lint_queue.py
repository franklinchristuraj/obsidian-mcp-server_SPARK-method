"""Lint Queue composer: normalize lint_vault + graph_health into id'd findings."""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional, Tuple

from src.apps.composers import call_vault, require_scope
from src.apps.contracts.lint_queue import (
    LintFinding,
    LintHealth,
    LintQueuePayload,
    ProposedFix,
)
from src.tools.obsidian_tools import obsidian_tools
from src.vault_intelligence.entity_index import EntityIndex

CATEGORY_ORDER = (
    "broken_link",
    "alias_collision",
    "orphan_entity",
    "missing_frontmatter",
    "missing_connections",
    "naming_drift",
)


def _finding_id(category: str, note_path: str, detail: str) -> str:
    raw = f"{category}|{note_path}|{detail}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
    prefix = {
        "broken_link": "bl",
        "alias_collision": "ac",
        "orphan_entity": "oe",
        "missing_frontmatter": "mf",
        "missing_connections": "mc",
        "naming_drift": "nd",
    }.get(category, "xx")
    return f"{prefix}-{digest}"


async def _proposed_link_fix(
    scope: str, note_path: str, link: str
) -> Tuple[bool, Optional[ProposedFix]]:
    """Classify whether a broken link can be auto-rewritten unambiguously."""
    intel = obsidian_tools._get_vault_intel()
    corpus_notes = await intel._all_notes(scope, include_sections=False)
    index = EntityIndex(corpus_notes)
    status, target_path = index.classify_link(link)
    if status == "resolved" and target_path:
        from pathlib import Path

        after = Path(target_path).stem
        return True, ProposedFix(
            kind="rewrite_link",
            before=f"[[{link}]]" if not link.startswith("[[") else link,
            after=f"[[{after}]]",
        )
    return False, None


async def build_findings(
    scope: str,
    lint: Dict[str, Any],
    categories: Optional[List[str]] = None,
) -> List[LintFinding]:
    allowed = set(categories) if categories else set(CATEGORY_ORDER)
    findings: List[LintFinding] = []

    for entry in lint.get("broken_wikilinks") or []:
        if "broken_link" not in allowed:
            break
        if isinstance(entry, dict):
            note_path = entry.get("source") or ""
            link = entry.get("link") or ""
            detail = f"[[{link}]] resolves to nothing" if link else "broken wikilink"
            auto, fix = await _proposed_link_fix(scope, note_path, link)
            findings.append(
                LintFinding(
                    id=_finding_id("broken_link", note_path, detail),
                    category="broken_link",
                    severity="high",
                    note_path=note_path,
                    detail=detail,
                    auto_fixable=auto,
                    proposed_fix=fix,
                )
            )

    for entry in lint.get("alias_collisions") or []:
        if "alias_collision" not in allowed:
            break
        if isinstance(entry, dict):
            alias = entry.get("alias") or ""
            paths = entry.get("paths") or []
            note_path = paths[0] if paths else ""
            detail = f"alias {alias!r} collides across {len(paths)} notes"
            findings.append(
                LintFinding(
                    id=_finding_id("alias_collision", note_path, detail),
                    category="alias_collision",
                    severity="high",
                    note_path=note_path,
                    detail=detail,
                    auto_fixable=False,
                )
            )

    for path in lint.get("orphan_entities") or []:
        if "orphan_entity" not in allowed:
            break
        detail = "orphan entity (no inbound links)"
        findings.append(
            LintFinding(
                id=_finding_id("orphan_entity", path, detail),
                category="orphan_entity",
                severity="medium",
                note_path=path,
                detail=detail,
                auto_fixable=False,
            )
        )

    for item in lint.get("missing_required_frontmatter") or []:
        if "missing_frontmatter" not in allowed:
            break
        text = str(item)
        note_path = text.split(" ", 1)[0]
        findings.append(
            LintFinding(
                id=_finding_id("missing_frontmatter", note_path, text),
                category="missing_frontmatter",
                severity="medium",
                note_path=note_path,
                detail=text,
                auto_fixable=False,
            )
        )

    for path in lint.get("missing_connections_section") or []:
        if "missing_connections" not in allowed:
            break
        detail = "missing ## Connections section"
        findings.append(
            LintFinding(
                id=_finding_id("missing_connections", path, detail),
                category="missing_connections",
                severity="low",
                note_path=path,
                detail=detail,
                auto_fixable=False,
            )
        )

    for item in (lint.get("invalid_event_type") or []) + (
        lint.get("invalid_touchpoint_type") or []
    ):
        if "naming_drift" not in allowed:
            break
        text = str(item)
        note_path = text.split(" ", 1)[0]
        findings.append(
            LintFinding(
                id=_finding_id("naming_drift", note_path, text),
                category="naming_drift",
                severity="medium",
                note_path=note_path,
                detail=text,
                auto_fixable=False,
            )
        )

    # Stable order by category then id
    order = {c: i for i, c in enumerate(CATEGORY_ORDER)}
    findings.sort(key=lambda f: (order.get(f.category, 99), f.id))
    return findings


async def compose_lint_queue(
    scope: str, categories: Optional[List[str]] = None
) -> Dict[str, Any]:
    scope = require_scope(scope)
    lint = await call_vault("lint_vault", scope=scope, folder="entities", fix=False)
    health_raw = await call_vault("graph_health", scope=scope)

    summary = lint.get("summary") or {}
    graph = health_raw.get("graph") or health_raw
    health = LintHealth(
        notes=int(summary.get("notes_scanned") or graph.get("notes") or 0),
        entities=int(graph.get("entities") or graph.get("nodes") or 0),
        edges=int(graph.get("edges") or 0),
        orphan_entities=int(summary.get("orphan_entities") or 0),
        broken_links=int(summary.get("broken_wikilinks") or 0),
        alias_collisions=int(summary.get("alias_collisions") or 0),
    )
    findings = await build_findings(scope, lint, categories)
    return LintQueuePayload(scope=scope, health=health, findings=findings).model_dump()
