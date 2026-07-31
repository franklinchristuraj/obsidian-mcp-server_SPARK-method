"""Vault intelligence MCP tools: resolve_entity, query_frontmatter, get_dossier, lint_vault."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import yaml

from src.scope import active_scopes_for_read, get_effective_workspace_context

from .corpus import ConcurrentModificationError, VaultCorpus
from .entity_index import EntityIndex, match_entities
from .graph import GraphIndex, as_link_list
from .parser import (
    CONNECTIONS_HEADING,
    EVENT_TYPES,
    EVENTS_HEADING,
    OPEN_QUESTIONS_HEADING,
    SNAPSHOT_MODE,
    SNAPSHOT_SOURCE,
    TOUCHPOINT_TYPES,
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
    "parent_engagement",
    "touchpoint_type",
    "channel",
    "adoption_stage",
    "requested_by",
    "technical_domains",
    "signal_confidence",
    "engagement_type",
    "stage",
    "status",
    "trial_start",
    "trial_end",
    "next_touch",
    "next_touch_type",
    "adoption_health",
    "adoption_outcome",
    "last_updated",
    "source_count",
)

CAP_EVENTS = 30

CAP_CONNECTIONS = 20
CAP_BACKLINKS = 20
CAP_QUERY_RESULTS = 50
CAP_DOSSIER_MENTIONS = 5
SNAPSHOT_MATCH_TOLERANCE_DAYS = 14
_SNAPSHOT_RESERVED_KEYS = frozenset({"org_id", "captured", "source", "mode"})
_IMPACT_FILTER_KEYS = frozenset({"why_called", "engagement_type", "owning_ve"})
_SAFE_ORG_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_REDACTED_METRIC_KEY_RE = re.compile(
    r"(?:^|_)(?:arr|customer|partner|person|name|email|revenue|price|amount)(?:_|$)",
    re.IGNORECASE,
)


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


def _parse_iso_date(value: Any, field: str = "date") -> date:
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD") from exc


def _window_key(days: int) -> str:
    return f"+{days}" if days > 0 else str(days)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _format_currency(value: float) -> str:
    if value >= 1_000_000:
        amount = f"{value / 1_000_000:.1f}".rstrip("0").rstrip(".")
        return f"${amount}M"
    if value >= 1_000:
        amount = f"{value / 1_000:.1f}".rstrip("0").rstrip(".")
        return f"${amount}K"
    return f"${value:,.0f}"


def _redact_metric_data(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _redact_metric_data(item)
            for key, item in value.items()
            if not _REDACTED_METRIC_KEY_RE.search(str(key))
        }
    if isinstance(value, list):
        return [_redact_metric_data(item) for item in value]
    return value


def _redact_windows(windows: Dict[str, dict]) -> Dict[str, dict]:
    redacted: Dict[str, dict] = {}
    for key, window in windows.items():
        safe = {
            field: value
            for field, value in window.items()
            if field
            in {
                "missing",
                "target_date",
                "window_days",
                "date",
                "offset_days",
                "mode",
                "source",
            }
        }
        if isinstance(window.get("metrics"), dict):
            safe["metrics"] = {
                metric: value
                for metric, value in window["metrics"].items()
                if _is_number(value)
                and not _REDACTED_METRIC_KEY_RE.search(str(metric))
            }
        redacted[key] = safe
    return redacted


def _paired_atomic_write(
    json_path: Path,
    json_content: str,
    markdown_path: Path,
    markdown_content: str,
) -> None:
    """Replace a snapshot pair, restoring the old pair if either replace fails."""
    json_path.parent.mkdir(parents=True, exist_ok=True)
    old_json = json_path.read_bytes() if json_path.is_file() else None
    old_markdown = markdown_path.read_bytes() if markdown_path.is_file() else None
    token = f"{os.getpid()}-{time.time_ns()}"
    json_tmp = json_path.parent / f".{json_path.name}.tmp-{token}"
    markdown_tmp = markdown_path.parent / f".{markdown_path.name}.tmp-{token}"

    try:
        json_tmp.write_text(json_content, encoding="utf-8")
        markdown_tmp.write_text(markdown_content, encoding="utf-8")
        os.replace(json_tmp, json_path)
        try:
            os.replace(markdown_tmp, markdown_path)
        except Exception:
            if old_json is None:
                json_path.unlink(missing_ok=True)
            else:
                restore = json_path.parent / f".{json_path.name}.restore-{token}"
                restore.write_bytes(old_json)
                os.replace(restore, json_path)
            raise
    except Exception:
        json_tmp.unlink(missing_ok=True)
        markdown_tmp.unlink(missing_ok=True)
        if old_markdown is not None and not markdown_path.is_file():
            restore = markdown_path.parent / f".{markdown_path.name}.restore-{token}"
            restore.write_bytes(old_markdown)
            os.replace(restore, markdown_path)
        raise


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

    async def _entity_notes(self, scope: Optional[str]) -> List[Any]:
        scopes = self._resolve_scopes(scope)
        notes: List[Any] = []
        for s in scopes:
            # load_scope does a filesystem walk + stat/parse per file (only
            # re-parsing what changed, but always re-listing the directory) -
            # a real blocking syscall cost, especially on network/cloud-synced
            # vaults. Off the event loop so one large scan doesn't stall every
            # other concurrent request on this single-worker server.
            notes.extend(await asyncio.to_thread(self.corpus.load_scope, [s], folder="entities"))
        return notes

    async def _all_notes(
        self,
        scope: Optional[str],
        folder: Optional[str] = None,
        *,
        include_sections: bool = True,
    ) -> List[Any]:
        return await asyncio.to_thread(
            self.corpus.load_scope,
            self._resolve_scopes(scope),
            folder=folder,
            include_sections=include_sections,
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
            fm = target.frontmatter
            event_date = fm.get("event_date")
            if event_date:
                entry["event_date"] = str(event_date)
            for key in (
                "event_type",
                "touchpoint_type",
                "parent_engagement",
                "adoption_stage",
                "channel",
                "signal_confidence",
            ):
                val = fm.get(key)
                if val:
                    entry[key] = val if not isinstance(val, list) else list(val)
            domains = fm.get("technical_domains")
            if domains:
                entry["technical_domains"] = (
                    list(domains) if isinstance(domains, list) else [domains]
                )
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
        entities = await self._entity_notes(scope)
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

        corpus_notes = await self._all_notes(scope, include_sections=False)
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

        # Surface linked 12_engagements/ notes for customer/partner entities.
        engagements_raw: List[dict] = []
        if match.entity_type in ("customer", "partner", "company"):
            all_notes = await self._all_notes(scope, folder="12_engagements")
            target_key = normalize_path_key(match.path)
            stem = Path(match.path).stem.lower()
            for note in all_notes:
                if str(note.frontmatter.get("type", "")).strip().lower() != "engagement":
                    continue
                cust = note.frontmatter.get("customer") or ""
                partner = note.frontmatter.get("partner") or ""
                linked = False
                for ref in as_link_list(cust) + as_link_list(partner):
                    resolved = self._resolve_link(ref, scope, notes_by_key, name_index)
                    if resolved and normalize_path_key(resolved) == target_key:
                        linked = True
                        break
                    if normalize_path_key(ref) in (target_key, stem):
                        linked = True
                        break
                if not linked:
                    continue
                engagements_raw.append(
                    {
                        "path": note.path,
                        "display": Path(note.path).stem,
                        "engagement_type": note.frontmatter.get("engagement_type", ""),
                        "status": note.frontmatter.get("status", ""),
                        "stage": note.frontmatter.get("stage", ""),
                        "trial_start": note.frontmatter.get("trial_start", ""),
                        "trial_end": note.frontmatter.get("trial_end", ""),
                        "next_touch": note.frontmatter.get("next_touch", ""),
                        "next_touch_type": note.frontmatter.get("next_touch_type", ""),
                        "adoption_health": note.frontmatter.get("adoption_health", ""),
                        "adoption_outcome": note.frontmatter.get("adoption_outcome", ""),
                        "agent_context": note.agent_context,
                    }
                )
            engagements_raw.sort(
                key=lambda e: e.get("next_touch")
                or e.get("trial_end")
                or e.get("trial_start")
                or "",
                reverse=True,
            )
        engagements, eng_trunc, eng_total = _truncate(engagements_raw, CAP_EVENTS)

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
            "engagements": engagements,
            "engagements_truncated": eng_trunc,
            "engagements_total": eng_total,
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

        notes = await self._all_notes(scope, folder=folder)
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

    @staticmethod
    def _validate_org_id(org_id: str) -> str:
        normalized = str(org_id or "").strip()
        if not normalized:
            raise ValueError("org_id is required")
        if not _SAFE_ORG_ID_RE.fullmatch(normalized) or ".." in normalized:
            raise ValueError("org_id contains invalid characters")
        return normalized

    def _work_snapshot_root(self, org_id: str) -> Path:
        root = (
            self.corpus.vault_path / "work" / "12_engagements" / "_snapshots"
        ).resolve()
        target = (root / org_id).resolve()
        if root not in target.parents:
            raise ValueError("org_id resolves outside the snapshot folder")
        return target

    def _normalize_snapshot_input(
        self,
        org_id: str,
        date_value: str,
        metrics: dict,
        source: str,
        mode: str,
        scope: str,
    ) -> Tuple[str, str, str, str]:
        if scope != "work":
            raise ValueError("capture_snapshot only supports scope='work'")
        self._resolve_scopes("work")
        normalized_org_id = self._validate_org_id(org_id)
        captured = _parse_iso_date(date_value).isoformat()
        if not isinstance(metrics, dict):
            raise ValueError("metrics must be an object")
        collisions = sorted(_SNAPSHOT_RESERVED_KEYS.intersection(metrics))
        if collisions:
            raise ValueError(f"metrics contains reserved keys: {collisions}")
        normalized_source = str(source or "").strip().lower()
        if normalized_source not in SNAPSHOT_SOURCE:
            raise ValueError(f"source must be one of {sorted(SNAPSHOT_SOURCE)}")
        normalized_mode = str(mode or "").strip().lower()
        if normalized_mode not in SNAPSHOT_MODE:
            raise ValueError(f"mode must be one of {sorted(SNAPSHOT_MODE)}")
        return normalized_org_id, captured, normalized_source, normalized_mode

    @staticmethod
    def _snapshot_contents(
        org_id: str,
        captured: str,
        metrics: dict,
        source: str,
        mode: str,
    ) -> Tuple[str, str]:
        payload = {
            "org_id": org_id,
            "captured": captured,
            **metrics,
            "source": source,
            "mode": mode,
        }
        frontmatter = {
            "type": "metric-snapshot",
            **payload,
            "agent_context": (
                f"Metric snapshot for {org_id}, captured {captured} from {source}."
            ),
            "tags": ["metric-snapshot", "ctx/work"],
        }
        yaml_text = yaml.safe_dump(
            frontmatter, sort_keys=False, allow_unicode=True, default_flow_style=False
        ).rstrip()
        rows = "\n".join(
            f"| {key} | {json.dumps(value, ensure_ascii=False)} |"
            for key, value in metrics.items()
        )
        markdown = (
            f"---\n{yaml_text}\n---\n\n# Metric Snapshot — {captured}\n\n"
            f"| Metric | Value |\n|---|---:|\n{rows}\n"
        )
        return json.dumps(payload, indent=2, ensure_ascii=False) + "\n", markdown

    async def capture_snapshot(
        self,
        org_id: str,
        date: str,
        metrics: dict,
        source: str,
        mode: str,
        scope: str = "work",
    ) -> Dict[str, Any]:
        org_id, captured, source, mode = self._normalize_snapshot_input(
            org_id, date, metrics, source, mode, scope
        )
        json_text, markdown = self._snapshot_contents(
            org_id, captured, metrics, source, mode
        )
        directory = self._work_snapshot_root(org_id)
        json_path = directory / f"{captured}.json"
        markdown_path = directory / f"{captured}.md"
        existed = json_path.is_file() and markdown_path.is_file()
        await asyncio.to_thread(
            _paired_atomic_write,
            json_path,
            json_text,
            markdown_path,
            markdown,
        )
        self.corpus._invalidate(
            "work", f"12_engagements/_snapshots/{org_id}/{captured}.md"
        )
        return _json_result(
            {
                "org_id": org_id,
                "captured": captured,
                "source": source,
                "mode": mode,
                "json_path": f"12_engagements/_snapshots/{org_id}/{captured}.json",
                "markdown_path": f"12_engagements/_snapshots/{org_id}/{captured}.md",
                "operation": "updated" if existed else "created",
            }
        )

    @staticmethod
    def _load_snapshot_file(path: Path, org_id: str) -> Optional[dict]:
        try:
            captured = _parse_iso_date(path.stem)
            data = json.loads(path.read_text(encoding="utf-8"))
            valid = (
                isinstance(data, dict)
                and str(data.get("org_id") or "") == org_id
                and str(data.get("captured") or "") == captured.isoformat()
                and str(data.get("mode") or "") in SNAPSHOT_MODE
            )
            if not valid:
                return None
            return {
                "captured_date": captured,
                "date": captured.isoformat(),
                "mode": data["mode"],
                "source": data.get("source"),
                "metrics": {
                    key: value
                    for key, value in data.items()
                    if key not in _SNAPSHOT_RESERVED_KEYS
                },
            }
        except (OSError, ValueError, json.JSONDecodeError):
            logger.warning("Ignoring malformed snapshot: %s", path)
            return None

    def _load_snapshots(self, org_id: str) -> List[dict]:
        directory = self._work_snapshot_root(org_id)
        if not directory.is_dir():
            return []
        snapshots = [
            snapshot
            for path in directory.glob("*.json")
            if (snapshot := self._load_snapshot_file(path, org_id)) is not None
        ]
        return snapshots

    @staticmethod
    def _closest_snapshot(snapshots: List[dict], target: date) -> Optional[dict]:
        candidates = [
            snapshot
            for snapshot in snapshots
            if abs((snapshot["captured_date"] - target).days)
            <= SNAPSHOT_MATCH_TOLERANCE_DAYS
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda snapshot: (
                abs((snapshot["captured_date"] - target).days),
                snapshot["captured_date"],
            ),
        )

    @staticmethod
    def _metric_interval(
        metric: str,
        from_key: str,
        to_key: str,
        start: dict,
        finish: dict,
    ) -> dict:
        interval: Dict[str, Any] = {"from": from_key, "to": to_key}
        if start.get("missing") or finish.get("missing"):
            return {**interval, "missing": True}
        from_value = start["metrics"].get(metric)
        to_value = finish["metrics"].get(metric)
        if not _is_number(from_value) or not _is_number(to_value):
            return {**interval, "skipped": "nonnumeric_or_absent"}
        absolute = to_value - from_value
        interval.update(
            {
                "from_date": start["date"],
                "to_date": finish["date"],
                "from_mode": start["mode"],
                "to_mode": finish["mode"],
                "from_value": from_value,
                "to_value": to_value,
                "abs": absolute,
                "pct": (
                    round((absolute / from_value) * 100, 2)
                    if from_value != 0
                    else None
                ),
            }
        )
        if from_value == 0:
            interval["pct_undefined_reason"] = "zero_baseline"
        if start["mode"] != finish["mode"]:
            interval["mixed_mode"] = True
        return interval

    @staticmethod
    def _build_metric_deltas(
        window_order: List[str], windows: Dict[str, dict]
    ) -> Dict[str, List[dict]]:
        metric_names = sorted(
            {
                metric
                for window in windows.values()
                for metric in (window.get("metrics") or {})
            }
        )
        deltas: Dict[str, List[dict]] = {metric: [] for metric in metric_names}
        for from_key, to_key in zip(window_order, window_order[1:]):
            start = windows[from_key]
            finish = windows[to_key]
            for metric in metric_names:
                deltas[metric].append(
                    VaultIntelligenceTools._metric_interval(
                        metric, from_key, to_key, start, finish
                    )
                )
        return deltas

    @staticmethod
    def _normalize_engagement_path(engagement_path: str) -> str:
        normalized = str(engagement_path or "").replace("\\", "/").lstrip("/")
        path = Path(normalized)
        invalid = (
            not normalized
            or ".." in path.parts
            or not path.parts
            or path.parts[0] != "12_engagements"
            or "_snapshots" in path.parts
        )
        if invalid:
            raise ValueError("engagement_path must be a note in 12_engagements/")
        return normalized if path.suffix == ".md" else f"{normalized}.md"

    @staticmethod
    def _validate_windows(windows: Optional[List[int]]) -> List[int]:
        requested = [-30, 0, 30, 90] if windows is None else windows
        if not isinstance(requested, list) or not requested:
            raise ValueError("windows must be a non-empty list of integers")
        if any(isinstance(value, bool) or not isinstance(value, int) for value in requested):
            raise ValueError("windows must contain integers")
        if len(set(requested)) != len(requested):
            raise ValueError("windows must not contain duplicates")
        return requested

    def _resolve_snapshot_windows(
        self,
        engagement_date: date,
        requested: List[int],
        snapshots: List[dict],
    ) -> Tuple[List[str], Dict[str, dict]]:
        output: Dict[str, dict] = {}
        order: List[str] = []
        for offset in requested:
            key = _window_key(offset)
            order.append(key)
            target = engagement_date + timedelta(days=offset)
            match = self._closest_snapshot(snapshots, target)
            if match is None:
                output[key] = {
                    "missing": True,
                    "target_date": target.isoformat(),
                    "window_days": offset,
                }
                continue
            output[key] = {
                "date": match["date"],
                "target_date": target.isoformat(),
                "window_days": offset,
                "offset_days": (match["captured_date"] - target).days,
                "mode": match["mode"],
                "source": match["source"],
                "metrics": match["metrics"],
            }
        return order, output

    async def engagement_delta(
        self,
        engagement_path: str,
        windows: Optional[List[int]] = None,
        scope: str = "work",
    ) -> Dict[str, Any]:
        if scope != "work":
            raise ValueError("engagement_delta only supports scope='work'")
        self._resolve_scopes("work")
        normalized_path = self._normalize_engagement_path(engagement_path)
        note = await asyncio.to_thread(
            self.corpus.get_note, "work", normalized_path, include_sections=True
        )
        if note is None:
            raise ValueError(f"Engagement note not found: {normalized_path}")

        org_id = str(note.frontmatter.get("org_id") or "").strip()
        if not org_id:
            return _json_result(
                {
                    "error": "missing_org_id",
                    "engagement_path": normalized_path,
                    "windows": {},
                    "deltas": {},
                }
            )
        normalized_org_id = self._validate_org_id(org_id)
        engagement_date = _parse_iso_date(
            note.frontmatter.get("date"), field="engagement date"
        )
        requested = self._validate_windows(windows)
        snapshots = await asyncio.to_thread(self._load_snapshots, normalized_org_id)
        order, output_windows = self._resolve_snapshot_windows(
            engagement_date, requested, snapshots
        )
        return _json_result(
            {
                "org_id": normalized_org_id,
                "engagement_path": normalized_path,
                "engagement_date": engagement_date.isoformat(),
                "windows": output_windows,
                "deltas": self._build_metric_deltas(order, output_windows),
            }
        )

    @staticmethod
    def _future_followup_count(notes: List[Any]) -> int:
        today = date.today()
        count = 0
        for note in notes:
            if str(note.frontmatter.get("status") or "").lower() == "closed":
                continue
            has_future = False
            for key in ("followup_1", "followup_2", "followup_3"):
                raw = note.frontmatter.get(key)
                if not raw:
                    continue
                try:
                    has_future = _parse_iso_date(raw, field=key) >= today
                except ValueError:
                    continue
                if has_future:
                    break
            if has_future:
                count += 1
        return count

    @staticmethod
    def _aggregate_deltas(records: List[dict]) -> Dict[str, List[dict]]:
        buckets: Dict[Tuple[str, str, str], dict] = {}
        for record in records:
            for metric, intervals in record.get("deltas", {}).items():
                for interval in intervals:
                    if "abs" not in interval:
                        continue
                    key = (metric, interval["from"], interval["to"])
                    bucket = buckets.setdefault(
                        key,
                        {
                            "from": interval["from"],
                            "to": interval["to"],
                            "from_total": 0,
                            "to_total": 0,
                            "contributing_engagements": 0,
                            "modes": set(),
                        },
                    )
                    bucket["from_total"] += interval["from_value"]
                    bucket["to_total"] += interval["to_value"]
                    bucket["contributing_engagements"] += 1
                    bucket["modes"].update(
                        (interval["from_mode"], interval["to_mode"])
                    )
        aggregated: Dict[str, List[dict]] = {}
        for (metric, _from_key, _to_key), bucket in sorted(buckets.items()):
            absolute = bucket["to_total"] - bucket["from_total"]
            item = {
                **bucket,
                "abs": absolute,
                "pct": (
                    round((absolute / bucket["from_total"]) * 100, 2)
                    if bucket["from_total"] != 0
                    else None
                ),
                "modes": sorted(bucket["modes"]),
            }
            aggregated.setdefault(metric, []).append(item)
        return aggregated

    @staticmethod
    def _validate_rollup_input(
        from_date: str, to_date: str, filters: Optional[dict], scope: str
    ) -> Tuple[date, date, dict]:
        if scope != "work":
            raise ValueError("impact_rollup only supports scope='work'")
        start = _parse_iso_date(from_date, field="from")
        finish = _parse_iso_date(to_date, field="to")
        if start > finish:
            raise ValueError("from must be on or before to")
        active_filters = filters or {}
        if not isinstance(active_filters, dict):
            raise ValueError("filters must be an object")
        unsupported = sorted(set(active_filters) - _IMPACT_FILTER_KEYS)
        if unsupported:
            raise ValueError(f"unsupported filters: {unsupported}")
        return start, finish, active_filters

    def _select_rollup_notes(
        self, notes: List[Any], start: date, finish: date, filters: dict
    ) -> List[Any]:
        selected = []
        for note in notes:
            fm = note.frontmatter
            if str(fm.get("type") or "") != "engagement":
                continue
            try:
                note_date = _parse_iso_date(fm.get("date"))
            except ValueError:
                continue
            if start <= note_date <= finish and self._frontmatter_matches(
                fm, filters
            )[0]:
                selected.append(note)
        return selected

    @staticmethod
    def _delta_status(delta: dict) -> str:
        if delta.get("error") == "missing_org_id":
            return "skipped_no_org_id"
        if all(item.get("missing") for item in delta["windows"].values()):
            return "missing_snapshots"
        return "available"

    @staticmethod
    def _rollup_record(note: Any, delta: dict, redact: bool) -> dict:
        fm = note.frontmatter
        common = {
            "org_id": delta.get("org_id"),
            "date": str(fm.get("date") or ""),
            "engagement_type": fm.get("engagement_type"),
            "why_called": fm.get("why_called"),
            "delta_status": VaultIntelligenceTools._delta_status(delta),
        }
        if redact:
            return {
                **common,
                "windows": _redact_windows(delta.get("windows", {})),
                "deltas": _redact_metric_data(delta.get("deltas", {})),
            }
        details = {
            "engagement_path": note.path,
            "owning_ve": fm.get("owning_ve"),
            "customer": fm.get("customer"),
            "partner": fm.get("partner"),
            "arr_at_intake": fm.get("arr_at_intake"),
            "qualification_amount": fm.get("qualification_amount"),
            "outcome_amount": fm.get("outcome_amount"),
            "outcome_corroborated": fm.get("outcome_corroborated"),
            "followup_1": fm.get("followup_1"),
            "followup_2": fm.get("followup_2"),
            "followup_3": fm.get("followup_3"),
            "status": fm.get("status"),
            "windows": delta.get("windows", {}),
            "deltas": delta.get("deltas", {}),
        }
        return {**common, **details}

    @staticmethod
    def _contributed_pipeline(notes: List[Any]) -> float:
        return sum(
            float(note.frontmatter["outcome_amount"])
            for note in notes
            if note.frontmatter.get("outcome_corroborated") is True
            and _is_number(note.frontmatter.get("outcome_amount"))
        )

    async def impact_rollup(
        self,
        from_date: str,
        to_date: str,
        filters: Optional[dict] = None,
        redact: bool = False,
        scope: str = "work",
    ) -> Dict[str, Any]:
        start, finish, active_filters = self._validate_rollup_input(
            from_date, to_date, filters, scope
        )
        notes = await self._all_notes("work", folder="12_engagements")
        matched_notes = self._select_rollup_notes(
            notes, start, finish, active_filters
        )
        records: List[dict] = []
        for note in matched_notes:
            delta_result = await self.engagement_delta(note.path, scope="work")
            records.append(
                self._rollup_record(note, delta_result["metadata"], redact)
            )
        pipeline = self._contributed_pipeline(matched_notes)
        pending = self._future_followup_count(matched_notes)
        headline = (
            f"{len(matched_notes)} engagements, {_format_currency(pipeline)} "
            f"contributed pipeline, {pending} pending follow-up"
        )
        payload = {
            "from": start.isoformat(),
            "to": finish.isoformat(),
            "filters": (
                {
                    key: value
                    for key, value in active_filters.items()
                    if key in {"why_called", "engagement_type"}
                }
                if redact
                else active_filters
            ),
            "redacted": bool(redact),
            "engagement_count": len(matched_notes),
            "contributed_pipeline": pipeline,
            "pending_follow_up": pending,
            "headline": headline,
            "metric_deltas": self._aggregate_deltas(records),
            "records": records,
        }
        return _json_result(payload)

    async def get_dossier(
        self,
        name: str,
        scope: Optional[str] = None,
        depth: int = 1,
        since: Optional[str] = None,
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

        corpus_notes = await self._all_notes(scope, include_sections=False)
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
        all_mentions = mentions
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
            "engagements": entity_data.get("engagements", [])[
                : CAP_EVENTS if depth >= 1 else 0
            ],
            "recent_mentions": mentions,
            "recent_mentions_truncated": ment_trunc,
            "recent_mentions_total": ment_total,
            "open_questions": open_questions,
            "depth": depth,
        }
        if since:
            events_since = [
                e for e in entity_data.get("events", []) if (e.get("event_date") or "") >= since
            ]
            mentions_since = [m for m in all_mentions if m["date"] >= since]
            payload["since"] = since
            payload["changes_since"] = {
                "events": events_since,
                "mentions": mentions_since,
            }
        return _json_result(payload)

    async def timeline(
        self,
        name: str,
        scope: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> Dict[str, Any]:
        resolved = await self.resolve_entity(name, scope=scope)
        entity_data = json.loads(resolved["content"][0]["text"])
        if entity_data.get("disambiguation_required"):
            return resolved

        canonical = entity_data["canonical_path"]
        entity_scope = entity_data.get("scope") or (scope or "work")
        target_key = normalize_path_key(canonical)

        def in_range(date_str: str) -> bool:
            if not date_str:
                return False
            if start and date_str < start:
                return False
            if end and date_str > end:
                return False
            return True

        items: List[dict] = []

        for ev in entity_data.get("events", []):
            date = ev.get("event_date", "")
            if not in_range(date):
                continue
            item = {
                "date": date,
                "type": "event",
                "path": ev["path"],
                "summary": ev.get("agent_context_of_target") or ev.get("display"),
            }
            for key in (
                "event_type",
                "touchpoint_type",
                "parent_engagement",
                "adoption_stage",
                "channel",
            ):
                if ev.get(key):
                    item[key] = ev[key]
            items.append(item)

        for eng in entity_data.get("engagements", []):
            # Surface next_touch / trial milestones on the customer timeline.
            for date_key, label in (
                ("next_touch", "next_touch"),
                ("trial_end", "trial_end"),
                ("trial_start", "trial_start"),
            ):
                date = eng.get(date_key) or ""
                if not in_range(date):
                    continue
                items.append(
                    {
                        "date": date,
                        "type": f"engagement_{label}",
                        "path": eng["path"],
                        "summary": eng.get("agent_context") or eng.get("display"),
                        "engagement_type": eng.get("engagement_type", ""),
                        "adoption_health": eng.get("adoption_health", ""),
                        "next_touch_type": eng.get("next_touch_type", ""),
                    }
                )

        corpus_notes = await self._all_notes(scope, include_sections=False)
        notes_by_key = self.corpus.index_by_path(corpus_notes)
        name_index = self.corpus.index_by_name(corpus_notes)
        for note in corpus_notes:
            for entry in extract_source_history_entries(note):
                if not in_range(entry["date"]):
                    continue
                matched = False
                for link in entry["links"]:
                    if link_matches_target(link, canonical):
                        matched = True
                    else:
                        r = self._resolve_link(link, scope, notes_by_key, name_index)
                        matched = bool(r and normalize_path_key(r) == target_key)
                    if matched:
                        break
                if matched:
                    items.append(
                        {
                            "date": entry["date"],
                            "type": "mention",
                            "source_path": note.path,
                            "text": entry["text"][:200],
                        }
                    )

        seen_mod_paths = {canonical}
        for group in (entity_data.get("connections", []), entity_data.get("backlinks", [])):
            for c in group:
                path = c.get("path")
                if not path or path in seen_mod_paths:
                    continue
                seen_mod_paths.add(path)
                note = notes_by_key.get(normalize_path_key(path))
                if note is None:
                    continue
                last_updated = str(note.frontmatter.get("last_updated") or "")
                if in_range(last_updated):
                    items.append(
                        {
                            "date": last_updated,
                            "type": "note_modified",
                            "path": note.path,
                            "entity_type": note.entity_type,
                        }
                    )

        items.sort(key=lambda i: i["date"], reverse=True)
        return _json_result(
            {
                "canonical_path": canonical,
                "scope": entity_scope,
                "start": start,
                "end": end,
                "items": items,
                "count": len(items),
            }
        )

    # Fidelity ranking for last_touch: a linked note's `last_updated` can be
    # edited for reasons unrelated to this entity (typo fix, backlink
    # cleanup, unrelated section added) and outrank a real event or dated
    # mention purely on recency. Prefer event -> mention -> note_modified;
    # only fall back to note_modified (flagged) when nothing else exists.
    _LAST_TOUCH_TIER = {"event": 0, "mention": 1, "note_modified": 2}

    async def last_touch(self, name: str, scope: Optional[str] = None) -> Dict[str, Any]:
        timeline_result = await self.timeline(name, scope=scope)
        data = json.loads(timeline_result["content"][0]["text"])
        if data.get("disambiguation_required"):
            return timeline_result

        items = data.get("items", [])
        # `items` is already sorted newest-first by the timeline; picking
        # the first item matching the best available tier yields the most
        # recent item within that tier without needing to re-sort.
        best_tier = min(
            (self._LAST_TOUCH_TIER.get(i["type"], 99) for i in items), default=None
        )
        chosen = (
            next((i for i in items if self._LAST_TOUCH_TIER.get(i["type"], 99) == best_tier), None)
            if best_tier is not None
            else None
        )

        payload: Dict[str, Any] = {
            "canonical_path": data["canonical_path"],
            "last_touch": chosen,
        }
        if chosen is not None:
            payload["fallback_to_note_modified"] = chosen["type"] == "note_modified"
        return _json_result(payload)

    async def lint_vault(
        self,
        scope: Optional[str] = None,
        folder: Optional[str] = None,
        fix: bool = False,
    ) -> Dict[str, Any]:
        notes = await self._all_notes(scope, folder=folder or "entities")
        notes_by_key = self.corpus.index_by_path(notes)
        # Resolve bare links against the full scope corpus, not just the linted
        # folder, so event-style [[bare]] links to entities outside the scan
        # (and full-path links) are not falsely reported as broken.
        corpus_notes = await self._all_notes(scope, include_sections=False)
        resolver_by_key = self.corpus.index_by_path(corpus_notes)
        name_index = self.corpus.index_by_name(corpus_notes)

        missing_fm: List[str] = []
        missing_connections: List[str] = []
        broken_links: List[dict] = []
        invalid_event_type: List[str] = []
        invalid_touchpoint_type: List[str] = []
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
                tt = str(fm.get("touchpoint_type", "")).strip().lower()
                if tt and tt not in TOUCHPOINT_TYPES:
                    invalid_touchpoint_type.append(
                        f"{note.path} (touchpoint_type: {tt})"
                    )

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
                "invalid_touchpoint_type": len(invalid_touchpoint_type),
                "orphan_entities": len(orphans),
                "alias_collisions": len(alias_collisions),
            },
            "missing_required_frontmatter": missing_fm[:50],
            "missing_connections_section": missing_connections[:50],
            "broken_wikilinks": broken_links[:50],
            "invalid_event_type": invalid_event_type[:50],
            "invalid_touchpoint_type": invalid_touchpoint_type[:50],
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
                    current_text = await asyncio.to_thread(
                        self.corpus.read_text, note.scope, note.path
                    )
                    mtime = await asyncio.to_thread(
                        self.corpus.stat_mtime, note.scope, note.path
                    )
                    new_text, n = rewrite_wikilinks(current_text, rewrites)
                    if n:
                        await asyncio.to_thread(
                            self.corpus.write_note,
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

    def _match_or_result(
        self, name: str, entities: List[Any]
    ) -> Tuple[Optional[Any], Optional[Dict[str, Any]]]:
        """Resolve name via match_entities; on disambiguation/no-match returns
        (None, early_result) for the caller to return directly, else (match, None)."""
        match, disambiguation = match_entities(name, entities)
        if disambiguation:
            return None, _json_result(
                {"disambiguation_required": True, "query": name, "candidates": disambiguation}
            )
        if match is None:
            raise ValueError(f"No entity matched: {name!r}")
        return match, None

    async def get_neighbors(
        self,
        name: str,
        scope: Optional[str] = None,
        depth: int = 1,
        rel_type: Optional[str] = None,
        direction: str = "both",
    ) -> Dict[str, Any]:
        entities = await self._entity_notes(scope)
        if not entities:
            raise ValueError("No entity cards found in scope")
        match, early = self._match_or_result(name, entities)
        if early is not None:
            return early
        graph = GraphIndex(entities)
        return _json_result(
            graph.neighbors(match.path, depth=depth, rel_type=rel_type, direction=direction)
        )

    async def get_backlinks(self, name: str, scope: Optional[str] = None) -> Dict[str, Any]:
        entities = await self._entity_notes(scope)
        if not entities:
            raise ValueError("No entity cards found in scope")
        match, early = self._match_or_result(name, entities)
        if early is not None:
            return early
        graph = GraphIndex(entities)
        return _json_result(graph.backlinks(match.path))

    async def find_path(self, a: str, b: str, scope: Optional[str] = None) -> Dict[str, Any]:
        entities = await self._entity_notes(scope)
        if not entities:
            raise ValueError("No entity cards found in scope")
        match_a, early_a = self._match_or_result(a, entities)
        if early_a is not None:
            return early_a
        match_b, early_b = self._match_or_result(b, entities)
        if early_b is not None:
            return early_b
        graph = GraphIndex(entities)
        return _json_result(graph.shortest_path(match_a.path, match_b.path))

    async def graph_health(self, scope: Optional[str] = None) -> Dict[str, Any]:
        lint_result = await self.lint_vault(scope=scope, folder="entities", fix=False)
        lint_payload = json.loads(lint_result["content"][0]["text"])

        entities = await self._entity_notes(scope)
        graph = GraphIndex(entities)
        entity_index = graph.entity_index

        missing_entities: List[dict] = []
        seen_missing: set = set()
        for note in entities:
            if note.entity_type != "event":
                continue
            fm = note.frontmatter
            for field_name, raw in (
                ("customer", fm.get("customer")),
                ("organizations", fm.get("organizations")),
            ):
                for link in as_link_list(raw):
                    if entity_index.resolve_bare_or_path(link) is not None:
                        continue
                    key = link.strip().lower()
                    if key in seen_missing:
                        continue
                    seen_missing.add(key)
                    missing_entities.append(
                        {"name": link, "referenced_from": note.path, "field": field_name}
                    )

        payload = {
            "lint_summary": lint_payload["summary"],
            "graph": graph.health_summary(),
            "missing_entities": missing_entities,
            "missing_entities_count": len(missing_entities),
        }
        return _json_result(payload)

    _CONTEXT_TIER_RANK = {
        "engaged_with": 1,
        "attended": 1,
        "attendees": 1,
        "related_to": 2,
        "mention": 3,
    }
    _CONTEXT_TIER_LABEL = {1: "typed", 2: "related", 3: "mention"}

    @staticmethod
    def _approx_tokens(text: str) -> int:
        return max(1, len(text) // 4) if text else 0

    async def build_context(
        self,
        seed: str,
        scope: Optional[str] = None,
        depth: int = 1,
        token_budget: int = 4000,
    ) -> Dict[str, Any]:
        entities = await self._entity_notes(scope)
        if not entities:
            raise ValueError("No entity cards found in scope")

        match, disambiguation = match_entities(seed, entities)
        resolution = "entity"
        if disambiguation:
            return _json_result(
                {"disambiguation_required": True, "query": seed, "candidates": disambiguation}
            )
        if match is None:
            # No entity match at all: fall back to ranked free-text search.
            hits = await self.search_notes_ranked(seed, scope=scope, limit=1)
            if not hits:
                raise ValueError(f"No entity or note matched: {seed!r}")
            top = hits[0]
            found = self.corpus.get_note(top.get("scope") or (scope or "work"), top["path"])
            if found is None:
                raise ValueError(f"No entity or note matched: {seed!r}")
            match = found
            resolution = "search"
            if not any(normalize_path_key(e.path) == normalize_path_key(match.path) for e in entities):
                entities = entities + [match]

        graph = GraphIndex(entities)
        neighbor_result = graph.neighbors(match.path, depth=depth, direction="both")

        def best_tier(edge_types: List[str]) -> int:
            return min((self._CONTEXT_TIER_RANK.get(t, 3) for t in edge_types), default=3)

        ranked: List[dict] = []
        for n in neighbor_result.get("neighbors", []):
            node = graph.nodes.get(normalize_path_key(n["path"]))
            if node is None:
                continue
            ranked.append(
                {
                    "node": node,
                    "tier": best_tier(n["edge_types"]),
                    "hops": n["hops"],
                    "edge_types": n["edge_types"],
                    "degree": graph.degree(node.path),
                    "recency": node.sort_date(),
                }
            )
        # Stable multi-pass sort, least-significant key first: degree desc,
        # recency desc, hops asc, tier asc (edge strength: typed > related > mention).
        ranked.sort(key=lambda r: -r["degree"])
        ranked.sort(key=lambda r: r["recency"], reverse=True)
        ranked.sort(key=lambda r: r["hops"])
        ranked.sort(key=lambda r: r["tier"])

        core_content = "\n\n".join(
            part
            for part in (
                match.agent_context,
                match.sections.get(OPEN_QUESTIONS_HEADING, "").strip(),
                (match.body or "")[:1500].strip(),
            )
            if part
        )
        core_tokens = self._approx_tokens(core_content)

        pack: List[dict] = [
            {
                "path": match.path,
                "tier": "core",
                "hops": 0,
                "edge_types": [],
                "content": core_content,
                "tokens": core_tokens,
            }
        ]
        manifest = [match.path]
        tokens_used = core_tokens
        truncated = False

        for r in ranked:
            node = r["node"]
            content = node.agent_context or (node.body or "")[:200].strip()
            t = self._approx_tokens(content)
            if tokens_used + t > token_budget:
                truncated = True
                break
            pack.append(
                {
                    "path": node.path,
                    "tier": self._CONTEXT_TIER_LABEL.get(r["tier"], "mention"),
                    "hops": r["hops"],
                    "edge_types": r["edge_types"],
                    "content": content,
                    "tokens": t,
                }
            )
            manifest.append(node.path)
            tokens_used += t

        return _json_result(
            {
                "resolved": True,
                "seed": {"query": seed, "canonical_path": match.path, "resolution": resolution},
                "token_budget": token_budget,
                "tokens_used": tokens_used,
                "truncated": truncated,
                "context_pack": pack,
                "source_manifest": manifest,
            }
        )

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
