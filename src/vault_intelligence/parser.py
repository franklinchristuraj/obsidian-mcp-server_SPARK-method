"""Parse Obsidian notes into structured ParsedNote objects."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
H2_RE = re.compile(r"^## (.+)$", re.MULTILINE)
SOURCE_HISTORY_DATE_RE = re.compile(
    r"^\s*-\s*\[(\d{4}-\d{2}-\d{2})\]\s*[—\-–]\s*(.+)$", re.MULTILINE
)

REQUIRED_ENTITY_FM = frozenset(
    {"type", "created", "agent_context", "tags", "entity_type"}
)
CONNECTIONS_HEADING = "Connections"
SOURCE_HISTORY_HEADING = "Source History"
OPEN_QUESTIONS_HEADING = "Open Questions"


@dataclass
class ParsedNote:
    path: str  # workspace-relative, e.g. entities/customer/gojob.md
    scope: str
    frontmatter: dict
    aliases: List[str]
    body: str
    sections: Dict[str, str]
    outlinks: List[str]
    agent_context: str
    mtime: float = 0.0

    @property
    def entity_type(self) -> str:
        return str(self.frontmatter.get("entity_type", ""))

    @property
    def tags(self) -> List[str]:
        raw = self.frontmatter.get("tags") or []
        if isinstance(raw, list):
            return [str(t) for t in raw]
        return [str(raw)]

    def sort_date(self) -> str:
        return str(
            self.frontmatter.get("last_updated")
            or self.frontmatter.get("created")
            or ""
        )


def normalize_link_target(target: str) -> str:
    """Normalize wikilink target for lenient matching."""
    t = target.strip().replace("\\", "/")
    while t.startswith("./"):
        t = t[2:]
    return t


def normalize_path_key(path: str) -> str:
    """Case-insensitive path key without .md suffix."""
    p = normalize_link_target(path).lower()
    if p.endswith(".md"):
        p = p[:-3]
    return p


FM_FIELD_RE = re.compile(
    r"^(?P<key>agent_context|created|last_updated|entity_type|type|source_count|poc_stage|lifecycle_stage|poc_hypothesis):\s*(?P<val>.+?)\s*$",
    re.MULTILINE,
)


def _parse_frontmatter_fast(raw_fm: str) -> dict:
    """Regex-based frontmatter for corpus scans (avoids yaml overhead)."""
    fm: dict = {}
    for match in FM_FIELD_RE.finditer(raw_fm):
        key = match.group("key")
        val = match.group("val").strip()
        if val.startswith('"') and val.endswith('"'):
            val = val[1:-1]
        elif val.startswith("'") and val.endswith("'"):
            val = val[1:-1]
        fm[key] = val
    aliases_match = re.search(r"^aliases:\s*\[(.*?)\]\s*$", raw_fm, re.MULTILINE)
    if aliases_match:
        inner = aliases_match.group(1)
        fm["aliases"] = [a.strip().strip("'\"") for a in inner.split(",") if a.strip()]
    tags_match = re.search(r"^tags:\s*\n((?:\s+-\s+.+\n?)+)", raw_fm, re.MULTILINE)
    if tags_match:
        fm["tags"] = [
            line.split("-", 1)[1].strip()
            for line in tags_match.group(1).splitlines()
            if line.strip().startswith("-")
        ]
    return fm


def _normalize_fm_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _normalize_fm_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_fm_value(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def parse_note(
    filepath: Path,
    scope: str,
    workspace_rel: str,
    *,
    include_sections: bool = True,
    mtime: Optional[float] = None,
) -> ParsedNote:
    """Parse a markdown file into a ParsedNote."""
    text = filepath.read_text(encoding="utf-8", errors="replace")
    frontmatter: dict = {}
    body = text

    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            raw_fm = text[3:end]
            body = text[end + 4 :].lstrip("\n")
            if include_sections:
                try:
                    loaded = yaml.safe_load(raw_fm)
                    frontmatter = (
                        _normalize_fm_value(loaded) if isinstance(loaded, dict) else {}
                    )
                except yaml.YAMLError:
                    frontmatter = {}
            else:
                frontmatter = _parse_frontmatter_fast(raw_fm)

    sections: Dict[str, str] = {}
    if include_sections:
        parts = H2_RE.split(body)
        if parts:
            preamble = parts[0]
            i = 1
            while i + 1 < len(parts):
                heading = parts[i].strip()
                content = parts[i + 1]
                sections[heading] = content.strip()
                i += 2
            if preamble.strip() and not sections:
                sections[""] = preamble.strip()

    outlinks: List[str] = []
    seen: set = set()
    for match in WIKILINK_RE.finditer(body):
        target = normalize_link_target(match.group(1))
        if target and target not in seen:
            seen.add(target)
            outlinks.append(target)

    raw_aliases = frontmatter.get("aliases") or []
    aliases: List[str] = []
    if isinstance(raw_aliases, list):
        aliases = [str(a).strip().lower() for a in raw_aliases if str(a).strip()]
    elif raw_aliases:
        aliases = [str(raw_aliases).strip().lower()]

    agent_context = str(frontmatter.get("agent_context") or "")

    if mtime is None:
        try:
            mtime = filepath.stat().st_mtime
        except OSError:
            mtime = 0.0

    return ParsedNote(
        path=workspace_rel.replace("\\", "/"),
        scope=scope,
        frontmatter=frontmatter,
        aliases=aliases,
        body=body,
        sections=sections,
        outlinks=outlinks,
        agent_context=agent_context,
        mtime=mtime,
    )


def extract_section_links(note: ParsedNote, heading: str = CONNECTIONS_HEADING) -> List[str]:
    """Wikilink targets from a named H2 section."""
    content = note.sections.get(heading, "")
    if not content:
        return []
    links: List[str] = []
    seen: set = set()
    for match in WIKILINK_RE.finditer(content):
        target = normalize_link_target(match.group(1))
        if target and target not in seen:
            seen.add(target)
            links.append(target)
    return links


def extract_source_history_entries(note: ParsedNote) -> List[dict]:
    """Parse dated Source History lines: {date, text, links}."""
    content = note.sections.get(SOURCE_HISTORY_HEADING, "")
    if not content:
        content = note.body
    if not content:
        return []
    entries: List[dict] = []
    for match in SOURCE_HISTORY_DATE_RE.finditer(content):
        rest = match.group(2).strip()
        links = [normalize_link_target(m.group(1)) for m in WIKILINK_RE.finditer(rest)]
        entries.append({"date": match.group(1), "text": rest, "links": links})
    entries.sort(key=lambda e: e["date"], reverse=True)
    return entries


def link_matches_target(link: str, canonical_path: str) -> bool:
    """Lenient match: paths may differ by .md suffix or case."""
    return normalize_path_key(link) == normalize_path_key(canonical_path)


def resolve_link_to_note_path(link: str, notes_by_key: Dict[str, ParsedNote]) -> Optional[str]:
    """Resolve a wikilink to a workspace-relative note path if it exists."""
    key = normalize_path_key(link)
    if key in notes_by_key:
        return notes_by_key[key].path
    # try with/without entities prefix variants
    for candidate in (link, f"{link}.md" if not link.endswith(".md") else link):
        k = normalize_path_key(candidate)
        if k in notes_by_key:
            return notes_by_key[k].path
    return None
