"""Parse Obsidian notes into structured ParsedNote objects."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
H2_RE = re.compile(r"^## (.+)$", re.MULTILINE)
SOURCE_HISTORY_DATE_RE = re.compile(
    r"^\s*-\s*\[(\d{4}-\d{2}-\d{2})\]\s*[—\-–]\s*(.+)$", re.MULTILINE
)

REQUIRED_ENTITY_FM = frozenset(
    {"type", "created", "agent_context", "tags", "entity_type"}
)
# Per entity_type required-frontmatter overrides. Entity types absent here fall
# back to REQUIRED_ENTITY_FM. Events are a distinct first-class entity whose
# schema intentionally omits the legacy type/created/tags fields.
REQUIRED_ENTITY_FM_BY_TYPE: Dict[str, frozenset] = {
    "event": frozenset(
        {"entity_type", "event_type", "event_date", "agent_context", "last_updated"}
    ),
}
# Controlled vocabulary for event entity_type=event cards.
EVENT_TYPES = frozenset(
    {
        "discovery-call",
        "build-with-me",
        "poc-presentation",
        "workshop",
        "internal-sync",
        "all-hands",
        "demo",
        "partner-review",
        "technical-deep-dive",
        "other",
    }
)
# Controlled vocabulary for type:engagement notes in 12_engagements/.
ENGAGEMENT_TYPES = frozenset(
    {
        "build-with-me",
        "hackathon",
        "workshop",
        "consulting",
        "partner-review",
        "demo",
        "ve-assist",
        "technical-deep-dive",
        "delivery",
        "enablement",
    }
)
ENGAGEMENT_STATUSES = frozenset(
    {"prepping", "scheduled", "live", "debriefed", "closed"}
)
TOUCHPOINT_TYPES = frozenset(
    {
        "kickoff-workshop",
        "email-follow-up",
        "mid-trial-review",
        "support",
        "technical-question",
        "final-review",
        "ad-hoc",
    }
)
ADOPTION_STAGES = frozenset(
    {
        "trial-start",
        "building",
        "mid-trial",
        "pre-close",
        "converted",
        "churned",
        "extended",
    }
)
ADOPTION_HEALTH = frozenset(
    {"on-track", "at-risk", "stalled", "converted", "churned"}
)
SNAPSHOT_SOURCE = frozenset({"c360"})
SNAPSHOT_MODE = frozenset({"live", "reconstructed"})
CHANNELS = frozenset(
    {"workshop", "call", "email", "slack", "async", "office-hours"}
)
SIGNAL_CONFIDENCE = frozenset({"low", "medium", "high"})
CONNECTIONS_HEADING = "Connections"
SOURCE_HISTORY_HEADING = "Source History"
OPEN_QUESTIONS_HEADING = "Open Questions"
EVENTS_HEADING = "Events"
INTERACTIONS_HEADING = "Interactions"


def required_fm_for(entity_type: str) -> frozenset:
    """Required frontmatter keys for an entity_type (per-type override or default)."""
    return REQUIRED_ENTITY_FM_BY_TYPE.get(
        str(entity_type or "").strip().lower(), REQUIRED_ENTITY_FM
    )


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
    frontmatter_links: List[str] = field(default_factory=list)
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
    """Normalize wikilink target for lenient matching.

    Three Obsidian-legal forms have to come off before a path lookup can
    succeed: the trailing backslash left behind by ``[[path\\|alias]]`` (the
    escape an aliased link needs to survive a markdown table), a
    ``#heading`` / ``#^block`` reference, and a trailing slash. Remaining
    backslashes are treated as Windows path separators.
    """
    t = target.strip().rstrip("\\")
    t = t.split("#", 1)[0].strip()
    t = t.replace("\\", "/")
    while t.startswith("./"):
        t = t[2:]
    return t.rstrip("/")


def normalize_path_key(path: str) -> str:
    """Case-insensitive path key without .md suffix."""
    p = normalize_link_target(path).lower()
    if p.endswith(".md"):
        p = p[:-3]
    return p


FM_FIELD_RE = re.compile(
    r"^(?P<key>agent_context|created|last_updated|entity_type|event_type|event_date|type|source_count|poc_stage|lifecycle_stage|poc_hypothesis|engagement_type|stage|status|trial_start|trial_end|next_touch|next_touch_type|adoption_health|adoption_outcome|adoption_stage|touchpoint_type|channel|parent_engagement|source_note|requested_by|owning_ve|sales_stage|signal_confidence|date):\s*(?P<val>.+?)\s*$",
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
    else:
        aliases_block = re.search(
            r"^aliases:[ \t]*\n((?:[ \t]+-[ \t]+.+\n?)+)", raw_fm, re.MULTILINE
        )
        if aliases_block:
            fm["aliases"] = [
                line.split("-", 1)[1].strip().strip("'\"")
                for line in aliases_block.group(1).splitlines()
                if line.strip().startswith("-")
            ]
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
    raw_fm = ""

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

    # Frontmatter wikilinks (event entities carry their graph edges here —
    # customer/organizations/participants/concepts — not in the body). Scan the
    # raw frontmatter text so this works in both full-YAML and fast-regex modes,
    # and merge into outlinks (deduped) so backlink traversal sees them.
    frontmatter_links: List[str] = []
    for match in WIKILINK_RE.finditer(raw_fm):
        target = normalize_link_target(match.group(1))
        if not target:
            continue
        if target not in frontmatter_links:
            frontmatter_links.append(target)
        if target not in seen:
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
        frontmatter_links=frontmatter_links,
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


def extract_all_wikilink_targets(content: str) -> List[str]:
    """All distinct wikilink targets across raw text (frontmatter + body),
    normalized. Unlike parse_note's outlinks (which scan frontmatter and body
    separately then merge), this runs one pass over unparsed content — used by
    write-time validation, which checks a note's links before it exists as a
    ParsedNote in the corpus.
    """
    targets: List[str] = []
    seen: set = set()
    for match in WIKILINK_RE.finditer(content):
        target = normalize_link_target(match.group(1))
        if target and target not in seen:
            seen.add(target)
            targets.append(target)
    return targets


def rewrite_wikilinks(content: str, rewrites: Dict[str, str]) -> Tuple[str, int]:
    """Rewrite ``[[old]]`` / ``[[old|display]]`` wikilinks to a canonical stem.

    ``rewrites`` maps normalized old link targets (as produced by
    normalize_link_target, matching what ``ParsedNote.outlinks`` holds) to
    their new canonical stems. One text-level regex pass covers both
    frontmatter and body; ``|display`` text is preserved untouched. Used by
    lint_vault(fix=True) to batch all rewrites for one file into a single
    read-modify-write. Returns (new_content, count_rewritten).
    """
    if not rewrites:
        return content, 0
    count = 0

    def _sub(match: re.Match) -> str:
        nonlocal count
        raw_target = match.group(1)
        display = match.group(2)
        key = normalize_link_target(raw_target)
        new_target = rewrites.get(key)
        if new_target is None:
            return match.group(0)
        count += 1
        if display is not None:
            return f"[[{new_target}|{display}]]"
        return f"[[{new_target}]]"

    new_content = WIKILINK_RE.sub(_sub, content)
    return new_content, count


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
