"""Shared name/alias/path resolution for wikilinks and entity lookup.

Extracted from VaultIntelligenceTools._match_entities/_resolve_link and
VaultCorpus.index_by_name so the same resolution primitives can back both
existing read tools (resolve_entity, get_dossier, lint_vault) and new
write-time consumers (write-time validation, lint_vault(fix=True)) without
duplicating the matching logic.
"""
from __future__ import annotations

from difflib import SequenceMatcher
from pathlib import Path
import re
from typing import Dict, List, Optional, Set, Tuple

from .parser import ParsedNote, normalize_link_target, normalize_path_key

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


def kebab_stem(path: str) -> str:
    return Path(path).stem.lower()


def build_name_index(notes: List[ParsedNote]) -> Tuple[Dict[str, ParsedNote], Set[str]]:
    """Map bare filename-stems and aliases to ParsedNote for bare-wikilink resolution.

    Event entities use bare links like ``[[claroty]]`` (Obsidian alias
    resolution) instead of full-path links. This index lets the intelligence
    tools resolve those to canonical ``entities/...`` paths. Keys that collide
    across two different notes are dropped so a bare link never resolves to an
    ambiguous target; the dropped keys are returned separately so callers that
    care about the distinction (lint's fix mode) can tell "ambiguous" apart
    from "not found" instead of seeing both as a plain miss.
    """
    idx: Dict[str, ParsedNote] = {}
    ambiguous: Set[str] = set()

    def _add(key: str, note: ParsedNote) -> None:
        k = key.strip().lower()
        if not k or k in ambiguous:
            return
        existing = idx.get(k)
        if existing is not None and existing.path != note.path:
            del idx[k]
            ambiguous.add(k)
            return
        idx[k] = note

    for note in notes:
        _add(Path(note.path).stem, note)
        for alias in note.aliases:
            _add(alias, note)
    return idx, ambiguous


class EntityIndex:
    """Read-only name/alias/path resolution over a snapshot of parsed notes.

    Built fresh per call from an already-loaded note list — no separate cache
    layer, matching the vault's own "631 notes, full rebuild is milliseconds"
    scale (see PRD_ziksaka-knowledge-graph.md).
    """

    def __init__(self, notes: List[ParsedNote]):
        self.notes = notes
        self.by_path: Dict[str, ParsedNote] = {
            normalize_path_key(n.path): n for n in notes
        }
        self.by_name, self.ambiguous_names = build_name_index(notes)

    def classify_link(self, link: str) -> Tuple[str, Optional[str]]:
        """Classify a wikilink target as ('resolved', path) / ('ambiguous', None)
        / ('unresolvable', None).

        Exact matching only (no fuzzy, no filesystem fallback): first a
        full/normalized path match, then the filename-stem extracted from the
        link text regardless of whether it contains "/" — which lets a stale
        full-path link whose target moved folders (e.g. a folder rename) still
        resolve by its bare filename, unlike the stricter no-slash bare-link
        step used elsewhere for reads.
        """
        note = self.by_path.get(normalize_path_key(link))
        if note is not None:
            return "resolved", note.path
        stem = Path(normalize_link_target(link)).stem.strip().lower()
        if stem in self.ambiguous_names:
            return "ambiguous", None
        named = self.by_name.get(stem)
        if named is not None:
            return "resolved", named.path
        return "unresolvable", None

    def resolve_bare_or_path(self, link: str) -> Optional[str]:
        """Exact stem/alias-or-path resolution, no fuzzy matching.

        Deliberately more lenient than the no-slash bare-link step inside
        VaultIntelligenceTools._resolve_link (extracts the filename-stem even
        from a full-path-shaped link). Used only by write-time validation and
        lint_vault(fix=True) — never by resolve_entity/get_dossier/lint_vault's
        read paths, so tightening or loosening this primitive can't silently
        change existing read-tool output.
        """
        status, path = self.classify_link(link)
        return path if status == "resolved" else None


def match_entities(
    name: str, entities: List[ParsedNote]
) -> Tuple[Optional[ParsedNote], List[dict]]:
    """Resolve an entity-name query against a candidate list: filename -> alias
    -> fuzzy. Returns (match, disambiguation). Moved verbatim from
    VaultIntelligenceTools._match_entities."""
    query = name.strip()
    if not query:
        raise ValueError("name cannot be empty")

    query_lower = query.lower()
    query_kebab = re.sub(r"[^a-z0-9]+", "-", query_lower).strip("-")

    # 1. Exact filename stem
    exact = [e for e in entities if kebab_stem(e.path) == query_kebab]
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

    # 3. Fuzzy over filename stem AND aliases (best score per entity)
    fuzzy: List[Tuple[float, ParsedNote]] = []
    for e in entities:
        candidates = [kebab_stem(e.path)]
        candidates.extend(
            re.sub(r"[^a-z0-9]+", "-", a.lower()).strip("-") for a in e.aliases
        )
        best: Optional[float] = None
        for cand in candidates:
            if not cand:
                continue
            if query_kebab in cand or cand in query_kebab:
                # Containment is a strong signal, but a flat score here made
                # every filename that merely happens to contain the query
                # (e.g. query "gojo" inside "gojob", "gojob-discovery-call",
                # "gojob-credential-handling-concern") tie for first place.
                # Scale by how much of the longer string the shorter one
                # actually covers, so "gojo" -> "gojob" (tight match) scores
                # well above "gojo" -> a 30-char event/pain-point filename
                # that merely embeds the same substring.
                shorter, longer = sorted((len(query_kebab), len(cand)))
                coverage = shorter / longer if longer else 1.0
                best = max(best or 0.0, 0.85 + 0.1 * coverage)
                continue
            dist = _levenshtein(query_kebab, cand)
            ratio = SequenceMatcher(None, query_kebab, cand).ratio()
            if dist <= FUZZY_MAX_DISTANCE or ratio >= FUZZY_MIN_RATIO:
                best = max(best or 0.0, ratio)
        if best is not None:
            fuzzy.append((best, e))

    fuzzy.sort(key=lambda x: x[0], reverse=True)
    if not fuzzy:
        return None, []

    top_ratio = fuzzy[0][0]
    top = [e for r, e in fuzzy if r >= top_ratio - 0.05]
    if len(top) == 1:
        return top[0], []
    return None, [{"path": e.path, "entity_type": e.entity_type, "match": "fuzzy"} for e in top[:5]]
