"""Vault intelligence MCP tools: resolve_entity, query_frontmatter, get_dossier, lint_vault."""
from __future__ import annotations

import json
import logging
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.scope import active_scopes_for_read, get_effective_workspace_context

from .corpus import VaultCorpus
from .parser import (
    CONNECTIONS_HEADING,
    OPEN_QUESTIONS_HEADING,
    REQUIRED_ENTITY_FM,
    extract_section_links,
    extract_source_history_entries,
    link_matches_target,
    normalize_path_key,
)

logger = logging.getLogger(__name__)

KEY_FRONTMATTER_FIELDS = (
    "entity_type",
    "poc_stage",
    "lifecycle_stage",
    "poc_hypothesis",
    "last_updated",
    "source_count",
)

CAP_CONNECTIONS = 20
CAP_BACKLINKS = 20
CAP_QUERY_RESULTS = 50
CAP_DOSSIER_MENTIONS = 5
FUZZY_MAX_DISTANCE = 3
FUZZY_MIN_RATIO = 0.72


def _levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        return _levenshtein(b, a)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = curr
    return prev[-1]


def _json_result(payload: Any) -> Dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, indent=2, ensure_ascii=False)}],
        "metadata": payload if isinstance(payload, dict) else {"result": payload},
    }


def _truncate(items: List[Any], cap: int) -> Tuple[List[Any], bool, int]:
    total = len(items)
    if total <= cap:
        return items, False, total
    return items[:cap], True, total


def _sort_by_last_updated(notes: List[Any], key_fn) -> List[Any]:
    return sorted(notes, key=key_fn, reverse=True)


class VaultIntelligenceTools:
    """Structured vault retrieval tools backed by live parse + mtime cache."""

    def __init__(self, vault_path: str):
        self.corpus = VaultCorpus(vault_path)

    def _resolve_scopes(self, scope: Optional[str]) -> List[str]:
        ctx = get_effective_workspace_context()
        try:
            return active_scopes_for_read(scope, tuple(ctx.allowed_scopes))
        except (ValueError, PermissionError) as e:
            if isinstance(e, PermissionError):
                raise ValueError("Access denied") from e
            raise ValueError(str(e)) from e

    def _entity_notes(self, scope: Optional[str]) -> List[Any]:
        scopes = self._resolve_scopes(scope)
        notes: List[Any] = []
        for s in scopes:
            notes.extend(self.corpus.load_scope([s], folder="entities"))
        return notes

    def _all_notes(
        self,
        scope: Optional[str],
        folder: Optional[str] = None,
        *,
        include_sections: bool = True,
    ) -> List[Any]:
        return self.corpus.load_scope(
            self._resolve_scopes(scope), folder=folder, include_sections=include_sections
        )

    def _kebab_stem(self, path: str) -> str:
        name = Path(path).stem.lower()
        return name

    def _match_entities(
        self, name: str, entities: List[Any]
    ) -> Tuple[Optional[Any], List[dict]]:
        """Resolution: filename → alias → fuzzy. Returns (match, disambiguation)."""
        query = name.strip()
        if not query:
            raise ValueError("name cannot be empty")

        query_lower = query.lower()
        query_kebab = re.sub(r"[^a-z0-9]+", "-", query_lower).strip("-")

        # 1. Exact filename stem
        exact = [e for e in entities if self._kebab_stem(e.path) == query_kebab]
        if len(exact) == 1:
            return exact[0], []
        if len(exact) > 1:
            return None, [{"path": e.path, "entity_type": e.entity_type} for e in exact]

        # 2. Alias match (case-insensitive)
        alias_hits = []
        for e in entities:
            if query_lower in e.aliases:
                alias_hits.append(e)
        if len(alias_hits) == 1:
            return alias_hits[0], []
        if len(alias_hits) > 1:
            return None, [{"path": e.path, "entity_type": e.entity_type, "match": "alias"} for e in alias_hits]

        # 3. Fuzzy filename
        fuzzy: List[Tuple[float, Any]] = []
        for e in entities:
            stem = self._kebab_stem(e.path)
            if query_kebab in stem or stem in query_kebab:
                fuzzy.append((0.9, e))
                continue
            dist = _levenshtein(query_kebab, stem)
            ratio = SequenceMatcher(None, query_kebab, stem).ratio()
            if dist <= FUZZY_MAX_DISTANCE or ratio >= FUZZY_MIN_RATIO:
                fuzzy.append((ratio, e))

        fuzzy.sort(key=lambda x: x[0], reverse=True)
        if not fuzzy:
            return None, []

        top_ratio = fuzzy[0][0]
        top = [e for r, e in fuzzy if r >= top_ratio - 0.05]
        if len(top) == 1:
            return top[0], []
        return None, [{"path": e.path, "entity_type": e.entity_type, "match": "fuzzy"} for e in top[:5]]

    def _enrich_connection(
        self, link: str, notes_by_key: Dict[str, Any], scope: str
    ) -> dict:
        display = link.split("/")[-1].replace(".md", "")
        resolved = normalize_path_key(link)
        target = notes_by_key.get(resolved)
        path = link
        if target:
            path = target.path
            display = Path(target.path).stem
        else:
            for s in self._resolve_scopes(scope):
                vp = self.corpus.resolve_vault_path(s, link)
                if vp:
                    path = vp
                    note = self.corpus.get_note(s, vp)
                    if note:
                        target = note
                    break
        return {
            "path": path,
            "display": display,
            "agent_context_of_target": target.agent_context if target else "",
        }

    def _compute_backlinks(
        self, canonical_path: str, corpus_notes: List[Any], notes_by_key: Dict[str, Any]
    ) -> List[dict]:
        hits: List[dict] = []
        for note in corpus_notes:
            if note.path == canonical_path:
                continue
            for link in note.outlinks:
                if link_matches_target(link, canonical_path):
                    hits.append({"path": note.path, "agent_context": note.agent_context})
                    break

        def sort_key(h: dict) -> str:
            n = notes_by_key.get(normalize_path_key(h["path"]))
            return n.sort_date() if n else ""

        hits.sort(key=sort_key, reverse=True)
        return hits

    async def resolve_entity(self, name: str, scope: Optional[str] = None) -> Dict[str, Any]:
        entities = self._entity_notes(scope)
        if not entities:
            raise ValueError("No entity cards found in scope")

        match, disambiguation = self._match_entities(name, entities)
        if disambiguation:
            payload = {
                "disambiguation_required": True,
                "query": name,
                "candidates": disambiguation,
            }
            return _json_result(payload)
        if match is None:
            raise ValueError(f"No entity matched: {name!r}")

        if CONNECTIONS_HEADING not in match.sections:
            logger.warning("Entity %s missing ## Connections section", match.path)

        corpus_notes = self._all_notes(scope, include_sections=False)
        notes_by_key = self.corpus.index_by_path(corpus_notes)

        conn_links = extract_section_links(match)
        connections_raw = [
            self._enrich_connection(link, notes_by_key, scope) for link in conn_links
        ]
        connections_raw.sort(
            key=lambda c: notes_by_key.get(normalize_path_key(c["path"]), match).sort_date(),
            reverse=True,
        )
        connections, conn_trunc, conn_total = _truncate(connections_raw, CAP_CONNECTIONS)

        backlinks_raw = self._compute_backlinks(match.path, corpus_notes, notes_by_key)
        backlinks, bl_trunc, bl_total = _truncate(backlinks_raw, CAP_BACKLINKS)

        recent = extract_source_history_entries(match)[:3]

        key_fm = {k: match.frontmatter[k] for k in KEY_FRONTMATTER_FIELDS if k in match.frontmatter}

        payload = {
            "canonical_path": match.path,
            "scope": match.scope,
            "entity_type": match.entity_type,
            "aliases": match.frontmatter.get("aliases") or [],
            "agent_context": match.agent_context,
            "key_frontmatter": key_fm,
            "connections": connections,
            "connections_truncated": conn_trunc,
            "connections_total": conn_total,
            "backlinks": backlinks,
            "backlinks_truncated": bl_trunc,
            "backlinks_total": bl_total,
            "recent_mentions": recent,
        }
        return _json_result(payload)

    def _tag_matches(self, note_tags: List[str], tag_filter: str) -> bool:
        tf = tag_filter.strip().lower()
        for t in note_tags:
            tl = t.lower()
            if tl == tf or tl.endswith(f"/{tf}") or tf in tl:
                return True
        return False

    def _frontmatter_matches(self, fm: dict, filters: dict) -> Tuple[bool, dict]:
        matched: dict = {}
        for key, expected in filters.items():
            if key == "tag" or key == "tags":
                continue
            actual = fm.get(key)
            if actual is None:
                return False, {}
            if str(actual).lower() == str(expected).lower():
                matched[key] = actual
            else:
                return False, {}
        return True, matched

    async def query_frontmatter(
        self,
        filters: dict,
        scope: Optional[str] = None,
        folder: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not filters and not tag:
            raise ValueError("Provide filters and/or tag")

        notes = self._all_notes(scope, folder=folder)
        results: List[dict] = []

        for note in notes:
            fm = note.frontmatter
            ok, matched = self._frontmatter_matches(fm, filters or {})
            if not ok:
                continue
            if tag and not self._tag_matches(note.tags, tag):
                continue
            results.append(
                {
                    "path": note.path,
                    "scope": note.scope,
                    "agent_context": note.agent_context,
                    "matched_fields": matched,
                }
            )

        results.sort(key=lambda r: _note_sort_date(notes, r["path"]), reverse=True)

        capped, truncated, total = _truncate(results, CAP_QUERY_RESULTS)
        payload: dict = {
            "count": total,
            "returned": len(capped),
            "truncated": truncated,
            "results": capped,
        }
        if truncated:
            payload["note"] = f"Filter matched {total} notes; showing first {CAP_QUERY_RESULTS}."
        return _json_result(payload)

    async def get_dossier(
        self,
        name: str,
        scope: Optional[str] = None,
        depth: int = 1,
    ) -> Dict[str, Any]:
        resolved = await self.resolve_entity(name, scope=scope)
        text = resolved["content"][0]["text"]
        entity_data = json.loads(text)

        if entity_data.get("disambiguation_required"):
            return resolved

        canonical = entity_data["canonical_path"]
        entity_scope = entity_data.get("scope") or (scope or "work")
        entity_note = self.corpus.get_note(entity_scope, canonical)
        if not entity_note:
            raise ValueError(f"Entity not found: {canonical}")

        open_questions = entity_note.sections.get(OPEN_QUESTIONS_HEADING, "").strip()

        corpus_notes = self._all_notes(scope, include_sections=False)
        mentions: List[dict] = []
        for note in corpus_notes:
            for entry in extract_source_history_entries(note):
                for link in entry["links"]:
                    if link_matches_target(link, canonical):
                        mentions.append(
                            {
                                "date": entry["date"],
                                "source_path": note.path,
                                "text": entry["text"][:200],
                            }
                        )
                        break
        mentions.sort(key=lambda m: m["date"], reverse=True)
        mentions, ment_trunc, ment_total = _truncate(mentions, CAP_DOSSIER_MENTIONS)

        payload = {
            "entity": {
                "canonical_path": entity_data["canonical_path"],
                "entity_type": entity_data["entity_type"],
                "agent_context": entity_data["agent_context"],
                "key_frontmatter": entity_data["key_frontmatter"],
                "aliases": entity_data["aliases"],
            },
            "connections": entity_data["connections"][: CAP_CONNECTIONS if depth >= 1 else 0],
            "backlinks": entity_data["backlinks"][: CAP_BACKLINKS if depth >= 1 else 0],
            "recent_mentions": mentions,
            "recent_mentions_truncated": ment_trunc,
            "recent_mentions_total": ment_total,
            "open_questions": open_questions,
            "depth": depth,
        }
        return _json_result(payload)

    async def lint_vault(
        self,
        scope: Optional[str] = None,
        folder: Optional[str] = None,
        fix: bool = False,
    ) -> Dict[str, Any]:
        if fix:
            raise ValueError("fix=True is not implemented yet; run with fix=False (default)")

        notes = self._all_notes(scope, folder=folder or "entities")
        notes_by_key = self.corpus.index_by_path(notes)

        missing_fm: List[str] = []
        missing_connections: List[str] = []
        broken_links: List[dict] = []
        alias_map: Dict[str, List[str]] = {}
        inbound: Dict[str, int] = {normalize_path_key(n.path): 0 for n in notes}

        for note in notes:
            fm = note.frontmatter
            missing = REQUIRED_ENTITY_FM - set(fm.keys())
            if missing and note.path.startswith("entities/"):
                missing_fm.append(f"{note.path} (missing: {sorted(missing)})")
            if note.path.startswith("entities/") and CONNECTIONS_HEADING not in note.sections:
                missing_connections.append(note.path)

            for alias in note.aliases:
                alias_map.setdefault(alias, []).append(note.path)

            for link in note.outlinks:
                resolved = self.corpus.resolve_vault_path(note.scope, link)
                if resolved is None:
                    broken_links.append({"source": note.path, "link": link})
                else:
                    inbound[normalize_path_key(resolved)] = inbound.get(normalize_path_key(resolved), 0) + 1

        alias_collisions = [
            {"alias": a, "paths": paths}
            for a, paths in alias_map.items()
            if len(paths) > 1
        ]

        orphans = [
            n.path
            for n in notes
            if n.path.startswith("entities/")
            and inbound.get(normalize_path_key(n.path), 0) == 0
            and not extract_section_links(n)
        ]

        payload = {
            "summary": {
                "notes_scanned": len(notes),
                "missing_required_frontmatter": len(missing_fm),
                "missing_connections_section": len(missing_connections),
                "broken_wikilinks": len(broken_links),
                "orphan_entities": len(orphans),
                "alias_collisions": len(alias_collisions),
            },
            "missing_required_frontmatter": missing_fm[:50],
            "missing_connections_section": missing_connections[:50],
            "broken_wikilinks": broken_links[:50],
            "orphan_entities": orphans[:50],
            "alias_collisions": alias_collisions[:20],
        }
        return _json_result(payload)


def _note_sort_date(notes: List[Any], path: str) -> str:
    for n in notes:
        if n.path == path:
            return n.sort_date()
    return ""
