"""Vault intelligence MCP tools: resolve_entity, query_frontmatter, get_dossier, lint_vault."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from src.scope import active_scopes_for_read, get_effective_workspace_context

from .corpus import ConcurrentModificationError, VaultCorpus
from .entity_index import EntityIndex, match_entities
from .parser import (
    CONNECTIONS_HEADING,
    EVENT_TYPES,
    EVENTS_HEADING,
    OPEN_QUESTIONS_HEADING,
    extract_section_links,
    extract_source_history_entries,
    link_matches_target,
    normalize_path_key,
    required_fm_for,
    rewrite_wikilinks,
)

logger = logging.getLogger(__name__)

KEY_FRONTMATTER_FIELDS = (
    "entity_type",
    "event_type",
    "event_date",
    "customer",
    "poc_stage",
    "lifecycle_stage",
    "poc_hypothesis",
    "last_updated",
    "source_count",
)

CAP_EVENTS = 30

CAP_CONNECTIONS = 20
CAP_BACKLINKS = 20
CAP_QUERY_RESULTS = 50
CAP_DOSSIER_MENTIONS = 5


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


_WIKILINK_WRAP_RE = re.compile(r"^\[\[([^\]|]+)(?:\|[^\]]+)?\]\]$")


def _scalar_key(value: Any) -> str:
    """Normalize a scalar for comparison; unwraps a single [[wikilink]]."""
    s = str(value).strip()
    m = _WIKILINK_WRAP_RE.match(s)
    if m:
        s = m.group(1)
    return normalize_path_key(s)


def _scalar_match(actual: Any, expected: Any) -> bool:
    return _scalar_key(actual) == _scalar_key(expected)


def _range_matches(actual: Any, ops: Dict[str, Any]) -> bool:
    """Comparison operators for scalar fields (dates compare lexically, ISO-safe)."""
    for op, bound in ops.items():
        a: Any
        b: Any
        try:
            a, b = float(actual), float(bound)
        except (TypeError, ValueError):
            a, b = str(actual), str(bound)
        key = op.strip().lower()
        if key in ("gte", ">="):
            ok = a >= b
        elif key in ("lte", "<="):
            ok = a <= b
        elif key in ("gt", ">"):
            ok = a > b
        elif key in ("lt", "<"):
            ok = a < b
        elif key in ("eq", "=="):
            ok = a == b
        elif key in ("ne", "!="):
            ok = a != b
        else:
            return False
        if not ok:
            return False
    return True


def _value_matches(actual: Any, expected: Any) -> bool:
    """Match a frontmatter value against a filter expectation.

    - dict expected -> comparison operators (gte/lte/gt/lt/eq/ne) on a scalar
    - list actual   -> membership (any element matches, wikilink-aware)
    - otherwise     -> scalar equality (wikilink-aware)
    """
    if isinstance(expected, dict):
        if isinstance(actual, list):
            return any(_range_matches(item, expected) for item in actual)
        return _range_matches(actual, expected)
    if isinstance(actual, list):
        return any(_scalar_match(item, expected) for item in actual)
    return _scalar_match(actual, expected)


class VaultIntelligenceTools:
    """Structured vault retrieval tools backed by live parse + mtime cache."""

    def __init__(self, vault_path_or_corpus: Union[str, VaultCorpus]):
        """Accepts a vault path (builds its own corpus) or a shared VaultCorpus
        (e.g. from ObsidianTools, so writes via ObsidianClient are immediately
        visible here through the same mtime cache)."""
        if isinstance(vault_path_or_corpus, VaultCorpus):
            self.corpus = vault_path_or_corpus
        else:
            self.corpus = VaultCorpus(vault_path_or_corpus)

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

    def _resolve_link(
        self,
        link: str,
        scope: Optional[str],
        notes_by_key: Dict[str, Any],
        name_index: Dict[str, Any],
    ) -> Optional[str]:
        """Resolve a wikilink to a canonical workspace-relative path.

        Handles both legacy full-path links (``[[entities/customer/claroty.md]]``)
        and bare event-style links (``[[claroty]]``) via the name/alias index.
        O(1) dict lookups are tried before the filesystem fallback.
        """
        # 1. Full-path / normalized key.
        note = notes_by_key.get(normalize_path_key(link))
        if note is not None:
            return note.path
        # 2. Bare name / alias (event-style links).
        if "/" not in link:
            named = name_index.get(link.strip().lower())
            if named is not None:
                return named.path
        # 3. Filesystem full-path resolution per scope.
        for s in self._resolve_scopes(scope):
            vp = self.corpus.resolve_vault_path(s, link)
            if vp:
                return vp
        return None

    def _enrich_connection(
        self,
        link: str,
        notes_by_key: Dict[str, Any],
        name_index: Dict[str, Any],
        scope: Optional[str],
    ) -> dict:
        display = link.split("/")[-1].replace(".md", "")
        path = link
        target = None
        resolved = self._resolve_link(link, scope, notes_by_key, name_index)
        if resolved:
            path = resolved
            target = notes_by_key.get(normalize_path_key(resolved)) or name_index.get(
                Path(resolved).stem.lower()
            )
            if target is None:
                for s in self._resolve_scopes(scope):
                    note = self.corpus.get_note(s, resolved)
                    if note:
                        target = note
                        break
            if target:
                path = target.path
                display = Path(target.path).stem
        entry = {
            "path": path,
            "display": display,
            "entity_type_of_target": target.entity_type if target else "",
            "agent_context_of_target": target.agent_context if target else "",
        }
        if target is not None:
            event_date = target.frontmatter.get("event_date")
            if event_date:
                entry["event_date"] = str(event_date)
        return entry

    def _compute_backlinks(
        self,
        canonical_path: str,
        corpus_notes: List[Any],
        notes_by_key: Dict[str, Any],
        name_index: Dict[str, Any],
        scope: Optional[str],
    ) -> List[dict]:
        target_key = normalize_path_key(canonical_path)
        hits: List[dict] = []
        for note in corpus_notes:
            if note.path == canonical_path:
                continue
            for link in note.outlinks:
                # Fast path: link already matches the canonical path directly.
                if link_matches_target(link, canonical_path):
                    hits.append(self._backlink_entry(note))
                    break
                # Bare / full-path links resolved through the index.
                resolved = self._resolve_link(link, scope, notes_by_key, name_index)
                if resolved and normalize_path_key(resolved) == target_key:
                    hits.append(self._backlink_entry(note))
                    break

        def sort_key(h: dict) -> str:
            n = notes_by_key.get(normalize_path_key(h["path"]))
            return n.sort_date() if n else ""

        hits.sort(key=sort_key, reverse=True)
        return hits

    @staticmethod
    def _backlink_entry(note: Any) -> dict:
        return {
            "path": note.path,
            "entity_type": note.entity_type,
            "agent_context": note.agent_context,
        }

    async def resolve_entity(self, name: str, scope: Optional[str] = None) -> Dict[str, Any]:
        entities = self._entity_notes(scope)
        if not entities:
            raise ValueError("No entity cards found in scope")

        match, disambiguation = match_entities(name, entities)
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
        name_index = self.corpus.index_by_name(corpus_notes)

        conn_links = extract_section_links(match)
        connections_raw = [
            self._enrich_connection(link, notes_by_key, name_index, scope)
            for link in conn_links
        ]
        connections_raw.sort(
            key=lambda c: notes_by_key.get(normalize_path_key(c["path"]), match).sort_date(),
            reverse=True,
        )
        connections, conn_trunc, conn_total = _truncate(connections_raw, CAP_CONNECTIONS)

        backlinks_raw = self._compute_backlinks(
            match.path, corpus_notes, notes_by_key, name_index, scope
        )
        backlinks, bl_trunc, bl_total = _truncate(backlinks_raw, CAP_BACKLINKS)

        # ## Events back-ref block on customer/org/person/partner cards — surface
        # the entity's event timeline directly (links are bare, resolved via index).
        event_links = extract_section_links(match, EVENTS_HEADING)
        events_raw = [
            self._enrich_connection(link, notes_by_key, name_index, scope)
            for link in event_links
        ]
        events_raw.sort(key=lambda e: e.get("event_date") or "", reverse=True)
        events, events_trunc, events_total = _truncate(events_raw, CAP_EVENTS)

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
            "events": events,
            "events_truncated": events_trunc,
            "events_total": events_total,
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
            if _value_matches(actual, expected):
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
        notes_by_key = self.corpus.index_by_path(corpus_notes)
        name_index = self.corpus.index_by_name(corpus_notes)
        target_key = normalize_path_key(canonical)
        mentions: List[dict] = []
        for note in corpus_notes:
            for entry in extract_source_history_entries(note):
                matched = False
                for link in entry["links"]:
                    if link_matches_target(link, canonical):
                        matched = True
                    else:
                        resolved = self._resolve_link(
                            link, scope, notes_by_key, name_index
                        )
                        matched = bool(
                            resolved and normalize_path_key(resolved) == target_key
                        )
                    if matched:
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
            "events": entity_data.get("events", [])[: CAP_EVENTS if depth >= 1 else 0],
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
        notes = self._all_notes(scope, folder=folder or "entities")
        notes_by_key = self.corpus.index_by_path(notes)
        # Resolve bare links against the full scope corpus, not just the linted
        # folder, so event-style [[bare]] links to entities outside the scan
        # (and full-path links) are not falsely reported as broken.
        corpus_notes = self._all_notes(scope, include_sections=False)
        resolver_by_key = self.corpus.index_by_path(corpus_notes)
        name_index = self.corpus.index_by_name(corpus_notes)

        missing_fm: List[str] = []
        missing_connections: List[str] = []
        broken_links: List[dict] = []
        invalid_event_type: List[str] = []
        alias_map: Dict[str, List[str]] = {}
        inbound: Dict[str, int] = {normalize_path_key(n.path): 0 for n in notes}

        for note in notes:
            fm = note.frontmatter
            is_entity = note.path.startswith("entities/")
            missing = required_fm_for(note.entity_type) - set(fm.keys())
            if missing and is_entity:
                missing_fm.append(f"{note.path} (missing: {sorted(missing)})")
            if is_entity and CONNECTIONS_HEADING not in note.sections:
                missing_connections.append(note.path)

            # event_type controlled-vocabulary check for event cards.
            if note.entity_type == "event":
                et = str(fm.get("event_type", "")).strip().lower()
                if et and et not in EVENT_TYPES:
                    invalid_event_type.append(f"{note.path} (event_type: {et})")

            for alias in note.aliases:
                alias_map.setdefault(alias, []).append(note.path)

            for link in note.outlinks:
                resolved = self._resolve_link(
                    link, scope, resolver_by_key, name_index
                )
                if resolved is None:
                    broken_links.append({"source": note.path, "link": link})
                else:
                    key = normalize_path_key(resolved)
                    inbound[key] = inbound.get(key, 0) + 1

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
                "invalid_event_type": len(invalid_event_type),
                "orphan_entities": len(orphans),
                "alias_collisions": len(alias_collisions),
            },
            "missing_required_frontmatter": missing_fm[:50],
            "missing_connections_section": missing_connections[:50],
            "broken_wikilinks": broken_links[:50],
            "invalid_event_type": invalid_event_type[:50],
            "orphan_entities": orphans[:50],
            "alias_collisions": alias_collisions[:20],
        }

        if not fix:
            return _json_result(payload)

        # --- fix mode: rewrite what can be rewritten unambiguously ---
        entity_index = EntityIndex(corpus_notes)
        per_note_rewrites: Dict[str, Dict[str, str]] = {}
        rewritten_entries: List[dict] = []
        still_ambiguous: List[dict] = []
        still_unresolvable: List[dict] = []

        for entry in broken_links:
            link = entry["link"]
            status, target_path = entity_index.classify_link(link)
            if status == "resolved":
                canonical_stem = Path(target_path).stem
                per_note_rewrites.setdefault(entry["source"], {})[link] = canonical_stem
                rewritten_entries.append({**entry, "rewritten_to": canonical_stem})
            elif status == "ambiguous":
                still_ambiguous.append(entry)
            else:
                still_unresolvable.append(entry)

        write_errors: List[dict] = []
        async with self.corpus.write_lock():
            for source_path, rewrites in per_note_rewrites.items():
                note = notes_by_key.get(normalize_path_key(source_path))
                if note is None:
                    continue
                try:
                    current_text = self.corpus.read_text(note.scope, note.path)
                    mtime = self.corpus.stat_mtime(note.scope, note.path)
                    new_text, n = rewrite_wikilinks(current_text, rewrites)
                    if n:
                        self.corpus.write_note(
                            note.scope,
                            note.path,
                            new_text,
                            create_folders=False,
                            expected_mtime=mtime,
                        )
                except ConcurrentModificationError:
                    write_errors.append(
                        {
                            "path": source_path,
                            "error": "concurrent modification; retry lint_vault(fix=True)",
                        }
                    )
                except OSError as e:
                    write_errors.append({"path": source_path, "error": str(e)})

        # Re-scan post-fix so the returned summary/broken_wikilinks reflect the
        # actual on-disk state, not the pre-fix snapshot.
        rescanned = await self.lint_vault(scope=scope, folder=folder, fix=False)
        rescanned_payload = json.loads(rescanned["content"][0]["text"])
        rescanned_payload["fix_report"] = {
            "rewritten": rewritten_entries,
            "rewritten_count": len(rewritten_entries),
            "still_ambiguous": still_ambiguous,
            "still_ambiguous_count": len(still_ambiguous),
            "still_unresolvable": still_unresolvable,
            "still_unresolvable_count": len(still_unresolvable),
            "write_errors": write_errors,
        }
        return _json_result(rescanned_payload)

    async def search_notes_ranked(
        self,
        keyword: str,
        scope: Optional[str] = None,
        folder: Optional[str] = None,
        limit: int = 20,
        case_sensitive: bool = False,
    ) -> List[dict]:
        """Relevance-ranked keyword search over the parsed corpus.

        Far cheaper than re-reading every note over REST per call, and ranks
        title/alias/agent_context/frontmatter hits above plain body hits.
        """
        if not keyword.strip():
            raise ValueError("Keyword cannot be empty")

        scopes = self._resolve_scopes(scope)
        notes = self.corpus.load_scope(
            scopes, folder=(folder or None), include_sections=False
        )

        needle = keyword if case_sensitive else keyword.lower()

        def contains(haystack: str) -> bool:
            if not haystack:
                return False
            return needle in (haystack if case_sensitive else haystack.lower())

        results: List[dict] = []
        for note in notes:
            stem = Path(note.path).stem
            score = 0.0
            if contains(stem):
                score += 5.0
            if any(contains(a) for a in note.aliases):
                score += 4.0
            if contains(note.agent_context):
                score += 3.0
            for value in note.frontmatter.values():
                if isinstance(value, str) and contains(value):
                    score += 2.0
                    break
            body = note.body or ""
            body_hay = body if case_sensitive else body.lower()
            occurrences = body_hay.count(needle)
            if occurrences:
                score += 1.0 + min(occurrences, 5) * 0.2

            if score <= 0:
                continue

            modified = ""
            if note.mtime:
                modified = datetime.fromtimestamp(note.mtime).isoformat()
            results.append(
                {
                    "path": note.path,
                    "scope": note.scope,
                    "name": Path(note.path).name,
                    "entity_type": note.entity_type,
                    "agent_context": note.agent_context,
                    "score": round(score, 2),
                    "context": self._snippet(body, keyword, case_sensitive),
                    "size": len(body),
                    "modified": modified,
                    "folder": str(Path(note.path).parent) if "/" in note.path else "",
                }
            )

        results.sort(key=lambda r: (r["score"], r["modified"]), reverse=True)
        return results[: max(limit, 0)]

    @staticmethod
    def _snippet(content: str, keyword: str, case_sensitive: bool = False) -> str:
        if not content:
            return ""
        hay = content if case_sensitive else content.lower()
        needle = keyword if case_sensitive else keyword.lower()
        idx = hay.find(needle)
        if idx == -1:
            return content[:120].strip()
        start = max(0, idx - 50)
        end = min(len(content), idx + len(keyword) + 50)
        snippet = content[start:end].strip()
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."
        return snippet


def _note_sort_date(notes: List[Any], path: str) -> str:
    for n in notes:
        if n.path == path:
            return n.sort_date()
    return ""
