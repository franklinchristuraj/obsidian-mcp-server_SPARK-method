"""
Obsidian MCP Tools Implementation
Workspace-scoped vault tools using ObsidianClient
"""
import json
import os
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from src.clients.obsidian_client import ObsidianClient, ObsidianAPIError
from src.scope import (
    active_scopes_for_read,
    forbid_scope_prefix_in_agent_path,
    get_effective_workspace_context,
    resolve_scoped_path,
    resolve_write_scope,
    scoped_list_folder,
    strip_scope_prefix,
)
from src.vault_intelligence.tools import VaultIntelligenceTools
from src.vault_intelligence.parser import EVENT_TYPES, required_fm_for
from ..types import MCPTool
from ..utils.list_notes_time import note_mtime_in_window, resolve_list_notes_time_window


def _entity_write_warnings(rel_path: str, content: str) -> List[str]:
    """Non-blocking advisories for entity-card writes (schema + event vocab).

    Mirrors lint_vault's checks at write time so drift is caught at the source.
    Returns an empty list for non-entity notes or notes without entity_type.
    """
    if "entities/" not in rel_path:
        return []
    from ..utils.template_utils import template_detector

    fm, _ = template_detector.extract_frontmatter(content)
    if not fm:
        return []
    entity_type = str(fm.get("entity_type", "")).strip().lower()
    if not entity_type:
        return []
    warnings: List[str] = []
    missing = sorted(required_fm_for(entity_type) - set(fm.keys()))
    if missing:
        warnings.append(
            f"missing required frontmatter for entity_type={entity_type}: {missing}"
        )
    if entity_type == "event":
        event_type = str(fm.get("event_type", "")).strip().lower()
        if not event_type:
            warnings.append("event_type is empty (required, controlled vocabulary)")
        elif event_type not in EVENT_TYPES:
            warnings.append(
                f"event_type '{event_type}' is not in the controlled vocabulary "
                f"{sorted(EVENT_TYPES)}"
            )
    return warnings


_EVENT_LINE_DATE_RE = re.compile(r"\[\[(\d{4}-\d{2}-\d{2})")


def _upsert_events_section(
    content: str, event_stem: str, event_type: str, event_date: str
) -> Tuple[str, bool]:
    """Idempotently add an event back-ref to an entity card's ## Events block.

    Frontmatter is left byte-for-byte untouched (no YAML round-trip). Returns
    (new_content, changed). The block is inserted before ## Source History,
    else ## Connections, else appended; existing event lines are kept sorted
    date-descending and de-duplicated on the event filename.
    """
    new_line = f"- [[{event_stem}]] — {event_type}, {event_date}"

    head = ""
    body = content
    if content.startswith("---"):
        end = content.find("\n---", 3)
        if end != -1:
            cut = end + 4
            head = content[:cut]
            body = content[cut:]

    def _date_key(line: str) -> str:
        m = _EVENT_LINE_DATE_RE.search(line)
        return m.group(1) if m else ""

    section_re = re.compile(r"(?m)^##\s+Events\s*$")
    m = section_re.search(body)
    if m:
        start = m.end()
        nxt = re.search(r"(?m)^##\s+", body[start:])
        sec_end = start + nxt.start() if nxt else len(body)
        section = body[start:sec_end]
        lines = [
            ln.rstrip()
            for ln in section.splitlines()
            if ln.strip().startswith("- ")
        ]
        if any(event_stem in ln for ln in lines):
            return content, False
        lines.append(new_line)
        lines.sort(key=_date_key, reverse=True)
        new_section = "\n" + "\n".join(lines) + "\n"
        new_body = body[:start] + new_section + body[sec_end:]
    else:
        block = f"## Events\n{new_line}\n"
        anchor = re.search(r"(?m)^##\s+Source History\s*$", body) or re.search(
            r"(?m)^##\s+Connections\s*$", body
        )
        if anchor:
            pos = anchor.start()
            new_body = body[:pos] + block + "\n" + body[pos:]
        else:
            sep = "" if body.endswith("\n") else "\n"
            new_body = body + sep + "\n" + block

    return head + new_body, True


def _scope_schema_read() -> Dict[str, Any]:
    return {
        "type": "string",
        "enum": ["personal", "passion", "work"],
        "description": (
            "Workspace folder. Omit to include all workspaces allowed for this API key; "
            "set to narrow reads to one workspace."
        ),
    }


def _scope_schema_write() -> Dict[str, Any]:
    return {
        "type": "string",
        "enum": ["personal", "passion", "work"],
        "description": (
            "Target workspace. Required when this key can access more than one workspace."
        ),
    }


# Tool name -> ObsidianTools method name (single source of truth for routing + dispatch)
OBSIDIAN_TOOL_DISPATCH: Dict[str, str] = {
    "workspaces": "tool_workspaces",
    "vault_structure": "get_vault_structure",
    "list_notes": "list_notes",
    "list_journal": "list_journal",
    "search": "keyword_search",
    "read_note": "read_note",
    "create_note": "create_note",
    "update_note": "update_note",
    "append_note": "append_note",
    "note_exists": "check_note_exists",
    "delete_note": "delete_note",
    "resolve_entity": "resolve_entity",
    "query_frontmatter": "query_frontmatter",
    "get_dossier": "get_dossier",
    "lint_vault": "lint_vault",
    "capture": "capture_seed",
    "create_event": "create_event",
}

OBSIDIAN_ROUTED_TOOL_NAMES = frozenset(OBSIDIAN_TOOL_DISPATCH.keys())


class ObsidianTools:
    """Workspace-scoped Obsidian MCP tools."""

    def __init__(self):
        self.client = None
        self._vault_intel: Optional[VaultIntelligenceTools] = None
        self._initialize_client()

    def _get_vault_intel(self) -> VaultIntelligenceTools:
        if self._vault_intel is None:
            vault_path = ""
            if self.client:
                vault_path = self.client.vault_path
            if not vault_path:
                vault_path = os.getenv("OBSIDIAN_VAULT_PATH", "")
            if not vault_path:
                raise ValueError("OBSIDIAN_VAULT_PATH not configured")
            self._vault_intel = VaultIntelligenceTools(vault_path)
        return self._vault_intel

    def _initialize_client(self):
        """Initialize ObsidianClient with error handling"""
        try:
            self.client = ObsidianClient()
        except ValueError as e:
            # Client will be None if API key is not set
            print(f"Warning: ObsidianClient not initialized: {e}")
            self.client = None

    def get_tools(self) -> List[MCPTool]:
        """Register workspace-scoped Obsidian MCP tools (canonical names only)."""

        def _tool(
            name: str, description: str, properties: Dict[str, Any], required: List[str]
        ) -> MCPTool:
            return MCPTool(
                name=name,
                description=description,
                inputSchema={
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False,
                },
            )

        sr = _scope_schema_read()
        sw = _scope_schema_write()
        meeting_vars_desc = """Variables for template substitution. For meeting notes, supports smart structured data:
- title: Meeting title
- date: YYYY-MM-DD format
- time: HH:MM format
- meeting_type: Type (standup, planning, review, etc.)
- attendees: List of names or dicts with {name, role}
- agenda: List of agenda items
- discussion: Raw discussion text/transcript
- discussion_points: List of {topic, points[]}
- action_items: List of {task, assignee, due_date}
- decisions: List of decisions made
- follow_up: Follow-up notes
- notes: Additional observations
- related_links: List of wiki links

For other note types: title, date, datetime, time, project, area.

Note: Meeting notes intelligently parse freeform content and only include sections with data."""

        create_props = {
            "path": {
                "type": "string",
                "description": (
                    "Path relative to the workspace (e.g. '06_daily-notes/2026-04-11.md'). "
                    "Do not prefix with personal/passion/work — use scope instead."
                ),
            },
            "content": {
                "type": "string",
                "description": "Markdown body; frontmatter (---) is respected when present.",
            },
            "scope": sw,
            "create_folders": {
                "type": "boolean",
                "description": "Create parent folders if missing",
                "default": True,
            },
            "use_template": {
                "type": "boolean",
                "description": "Apply template from workspace 00_system/templates when appropriate",
                "default": True,
            },
            "template_vars": {
                "type": "object",
                "description": meeting_vars_desc,
                "additionalProperties": True,
            },
        }

        search_props = {
            "keyword": {
                "type": "string",
                "description": "Word or phrase to find in note bodies",
            },
            "folder": {
                "type": "string",
                "description": "Optional folder under the workspace (e.g. '03_areas')",
                "default": "",
            },
            "case_sensitive": {
                "type": "boolean",
                "description": "Case-sensitive match",
                "default": False,
            },
            "limit": {
                "type": "integer",
                "description": "Max notes to return",
                "default": 20,
                "minimum": 1,
                "maximum": 50,
            },
            "scope": sr,
        }

        journal_props = {
            "startDate": {
                "type": "string",
                "description": "Start date YYYY-MM-DD",
            },
            "endDate": {
                "type": "string",
                "description": "End date YYYY-MM-DD",
            },
            "scope": sr,
        }

        read_path_prop = {
            "path": {
                "type": "string",
                "description": "Note path relative to workspace (no personal/passion/work prefix)",
            },
            "scope": sr,
        }

        vault_props = {
            "use_cache": {
                "type": "boolean",
                "description": "Use cached vault structure when available",
                "default": True,
            },
            "scope": sr,
        }

        list_props = {
            "folder": {
                "type": "string",
                "description": "Optional folder under each workspace (empty = all notes in allowed workspaces)",
                "default": "",
            },
            "scope": sr,
            "modified_after": {
                "type": "string",
                "description": (
                    "Optional lower bound on file modification time (inclusive). "
                    "ISO date YYYY-MM-DD (start of that local day), ISO datetime, or keywords today / yesterday."
                ),
            },
            "modified_before": {
                "type": "string",
                "description": (
                    "Optional upper bound on file modification time (inclusive). "
                    "For date-only YYYY-MM-DD, includes the entire local calendar day."
                ),
            },
            "days": {
                "type": "number",
                "description": (
                    "Rolling window from now: keep notes modified within the last N days. "
                    "Combined with modified_after by using the stricter (more recent) cutoff."
                ),
            },
            "hours": {
                "type": "number",
                "description": "Rolling window from now: keep notes modified within the last N hours.",
            },
            "limit": {
                "type": "integer",
                "description": (
                    "Maximum notes to return after filters; results are most recently modified first when "
                    "any time filter or limit is set."
                ),
            },
        }

        update_props = {
            "path": {"type": "string", "description": "Note path relative to workspace"},
            "content": {"type": "string", "description": "Full new content"},
            "preserve_format": {
                "type": "boolean",
                "description": "Preserve YAML frontmatter / structure when possible",
                "default": True,
            },
            "scope": sw,
        }

        append_props = {
            "path": {"type": "string", "description": "Note path relative to workspace"},
            "content": {"type": "string", "description": "Text to append"},
            "separator": {
                "type": "string",
                "description": "Separator before appended text",
                "default": "\n\n",
            },
            "scope": sw,
        }

        delete_props = {
            "path": {"type": "string", "description": "Note path relative to workspace"},
            "scope": sw,
        }

        tools: List[MCPTool] = [
            _tool(
                "workspaces",
                (
                    "List workspace folders (scopes) allowed for this API key. "
                    "Call early in a session; then load MCP prompt vault_mcp_agent_guide for tool workflows."
                ),
                {},
                [],
            ),
            _tool(
                "vault_structure",
                "Folder tree with recursive note counts, filtered by allowed workspaces.",
                vault_props,
                [],
            ),
            _tool(
                "list_notes",
                (
                    "List notes with metadata (scoped). Optional filters use filesystem mtime: "
                    "modified_after, modified_before (ISO dates/datetimes or today/yesterday), "
                    "rolling days/hours, and limit (recent first)."
                ),
                list_props,
                [],
            ),
            _tool(
                "list_journal",
                "Daily notes in a date range with workspace tags (deduplicated). Requires startDate and endDate (YYYY-MM-DD).",
                journal_props,
                ["startDate", "endDate"],
            ),
            _tool(
                "search",
                "Keyword search in note bodies (scoped). Parameter is keyword (not query). For entities prefer resolve_entity.",
                search_props,
                ["keyword"],
            ),
            _tool(
                "read_note",
                "Read a note (scoped path).",
                read_path_prop,
                ["path"],
            ),
            _tool(
                "create_note",
                "Create a note in a workspace (scope required if key has multiple workspaces).",
                create_props,
                ["path", "content"],
            ),
            _tool(
                "update_note",
                "Replace note content (scope required if key has multiple workspaces).",
                update_props,
                ["path", "content"],
            ),
            _tool(
                "append_note",
                "Append to a note (scope required if key has multiple workspaces).",
                append_props,
                ["path", "content"],
            ),
            _tool(
                "note_exists",
                "Check if a note exists (scoped).",
                read_path_prop,
                ["path"],
            ),
            _tool(
                "delete_note",
                "Delete a note (scope required if key has multiple workspaces).",
                delete_props,
                ["path"],
            ),
            _tool(
                "resolve_entity",
                (
                    "PRIMARY tool for work entity lookup by name, alias, or fuzzy match "
                    "(e.g. Gojab → GoJob). Prefer over search+read_note fan-out. "
                    "Returns canonical path, agent_context, key frontmatter, connections "
                    "(with target agent_context), backlinks, recent Source History. "
                    "Use scope=work. Call read_note only when you need the full body."
                ),
                {
                    "name": {
                        "type": "string",
                        "description": "Entity name, alias, or partial filename (e.g. Gojab, gojob)",
                    },
                    "scope": sr,
                },
                ["name"],
            ),
            _tool(
                "query_frontmatter",
                (
                    "Filter notes by frontmatter (AND semantics) and optional tag. "
                    "Live file scan — do not rely on index.md. "
                    "Returns path + agent_context only (max 50), sorted by last_updated. "
                    "Scalar values match exactly (wikilink-aware); a list field matches by "
                    "membership (e.g. organizations: claroty); a value may also be a comparison "
                    "object {gte/lte/gt/lt/eq} for dates/numbers (e.g. event_date: {gte: 2026-04-01}). "
                    "Example: filters={entity_type: event, event_type: discovery-call}, scope=work, folder=entities/event."
                ),
                {
                    "filters": {
                        "type": "object",
                        "description": (
                            "Frontmatter key/value filters. Scalar = exact (wikilink-aware); "
                            "list field = membership; value can be {gte/lte/gt/lt/eq: ...} for ranges. "
                            "E.g. {entity_type: event, event_date: {gte: 2026-04-01, lte: 2026-06-30}}"
                        ),
                        "additionalProperties": True,
                    },
                    "scope": sr,
                    "folder": {
                        "type": "string",
                        "description": "Optional folder under workspace (e.g. entities/customer)",
                        "default": "",
                    },
                    "tag": {
                        "type": "string",
                        "description": "Optional tag filter (matches tags list, supports nested tags)",
                    },
                },
                ["filters"],
            ),
            _tool(
                "get_dossier",
                (
                    "Meeting-prep brief for an entity in one call. Wraps resolve_entity plus "
                    "open questions and recent mentions across the corpus. "
                    "Use scope=work. Prefer over manually chaining resolve_entity + read_note."
                ),
                {
                    "name": {
                        "type": "string",
                        "description": "Entity name (same fuzzy resolution as resolve_entity)",
                    },
                    "scope": sr,
                    "depth": {
                        "type": "integer",
                        "description": "Connection hop depth (default 1)",
                        "default": 1,
                    },
                },
                ["name"],
            ),
            _tool(
                "lint_vault",
                (
                    "Audit vault convention drift: missing frontmatter, missing ## Connections, "
                    "broken wikilinks, orphan entities, alias collisions. "
                    "Read-only by default (fix=false). Use before trusting entity graph tools on a new folder."
                ),
                {
                    "scope": sr,
                    "folder": {
                        "type": "string",
                        "description": "Folder to scan (default entities)",
                        "default": "entities",
                    },
                    "fix": {
                        "type": "boolean",
                        "description": "Apply safe mechanical fixes (default false)",
                        "default": False,
                    },
                },
                [],
            ),
            _tool(
                "capture",
                (
                    "Quick-capture to the root 01_seeds/ inbox (pre-scope) as a `type: capture` "
                    "note — no scope needed. Applies the vault capture template "
                    "(00_system/templates/capture.md) to write the canonical capture schema "
                    "(capture_type / source / captured / spark / status: inbox / target_scope) "
                    "with an `## Idea` / `## Why It Matters` body, so the item shows up in the triage dashboard. "
                    "Use for voice thoughts, saved posts, or excerpts not yet tied to a workspace. "
                    "Captures are promoted (move + reframe) into <scope>/01_seeds/ during weekly review."
                ),
                {
                    "title": {
                        "type": "string",
                        "description": "Optional short title — used to build the filename slug. If omitted, the slug is derived from the body.",
                        "default": "",
                    },
                    "content": {
                        "type": "string",
                        "description": "Body text — voice transcript, raw thought, post text, or excerpt",
                        "default": "",
                    },
                    "source": {
                        "type": "string",
                        "description": "Origin of this capture, e.g. voice, a URL, or an app name",
                        "default": "",
                    },
                    "capture_type": {
                        "type": "string",
                        "enum": ["thought", "post", "excerpt"],
                        "description": "Kind of capture. thought = voice/raw idea, post = saved link, excerpt = quoted text. Defaults to thought.",
                        "default": "thought",
                    },
                    "spark": {
                        "type": "string",
                        "description": "One-line 'why this matters' / why it was saved. REQUIRED for post and excerpt; optional for thought.",
                        "default": "",
                    },
                    "captured": {
                        "type": "string",
                        "description": "Optional ISO 8601 capture timestamp. Defaults to now.",
                        "default": "",
                    },
                },
                [],
            ),
            _tool(
                "create_event",
                (
                    "Create an event entity card in the work knowledge graph "
                    "(entities/event/). Builds the canonical "
                    "YYYY-MM-DD-{slug}-{event_type}.md filename (customer slug when "
                    "customer-facing, else org slug), a schema-valid frontmatter block "
                    "(graph edges as bare wikilinks), and a # title / > agent_context / "
                    "## Connections / ## Outcome body. By default it also idempotently "
                    "adds a ## Events back-ref to the linked customer / participants / "
                    "non-home organizations. Use scope=work."
                ),
                {
                    "event_type": {
                        "type": "string",
                        "enum": sorted(EVENT_TYPES),
                        "description": "Controlled vocabulary for the kind of interaction.",
                    },
                    "event_date": {
                        "type": "string",
                        "description": "YYYY-MM-DD. Defaults to today.",
                        "default": "",
                    },
                    "title": {
                        "type": "string",
                        "description": "Event title (H1). Derived from customer/org + type if omitted.",
                        "default": "",
                    },
                    "customer": {
                        "type": "string",
                        "description": "Customer name/slug for customer-facing events (drives filename slug). Omit for internal events.",
                        "default": "",
                    },
                    "organizations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Org names/slugs involved. Defaults to ['make'] if empty.",
                    },
                    "participants": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Person / internal-stakeholder names or slugs.",
                    },
                    "concepts": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Framework / topic slugs (optional).",
                    },
                    "agent_context": {
                        "type": "string",
                        "description": "One-line synthesized summary. Derived if omitted.",
                        "default": "",
                    },
                    "outcome": {
                        "type": "string",
                        "description": "What was decided / next step (## Outcome).",
                        "default": "",
                    },
                    "source_note": {
                        "type": "string",
                        "description": "Wikilink target for the source meeting/engagement note.",
                        "default": "",
                    },
                    "poc_stage": {
                        "type": "string",
                        "description": "Optional POC stage for pipeline timelines.",
                        "default": "",
                    },
                    "scope": sw,
                    "update_backrefs": {
                        "type": "boolean",
                        "description": "Add ## Events back-refs to linked entities (default true).",
                        "default": True,
                    },
                },
                ["event_type"],
            ),
        ]
        return tools

    # =================== Tool Implementations ===================

    async def tool_workspaces(self) -> Dict[str, Any]:
        """Scopes allowed for the current API key."""
        ctx = get_effective_workspace_context()
        payload = {
            "scopes": list(ctx.allowed_scopes),
            "role": ctx.role,
            "display_name": ctx.display_name,
        }
        return {
            "content": [{"type": "text", "text": json.dumps(payload, indent=2)}],
            "metadata": payload,
        }

    def _access_error(self, exc: BaseException) -> ValueError:
        if isinstance(exc, PermissionError):
            return ValueError("Access denied")
        return ValueError(str(exc))

    def _resolve_note_path_for_write(
        self,
        path: str,
        scope: Optional[str],
        *,
        normalize: bool = False,
    ) -> Tuple[str, str, str]:
        """Returns (vault_full_path, relative_path_for_display, workspace_scope)."""
        ctx = get_effective_workspace_context()
        allow = tuple(ctx.allowed_scopes)
        forbid_scope_prefix_in_agent_path(path)
        rel = path
        if normalize:
            from ..utils.template_utils import template_detector

            rel = template_detector.normalize_folder_path(path)
        try:
            ws = resolve_write_scope(scope, allow)
            full = resolve_scoped_path(rel, ws, allow)
        except (ValueError, PermissionError) as e:
            raise self._access_error(e) from e
        return full, rel, ws

    async def read_note(self, path: str, scope: Optional[str] = None) -> Dict[str, Any]:
        """Read note; path is relative to workspace. Resolves scope if omitted."""
        if not self.client:
            raise ValueError("Obsidian client not initialized. Check OBSIDIAN_API_KEY.")

        ctx = get_effective_workspace_context()
        allow = tuple(ctx.allowed_scopes)
        try:
            forbid_scope_prefix_in_agent_path(path)
            active = active_scopes_for_read(scope, allow)
        except (ValueError, PermissionError) as e:
            raise self._access_error(e) from e

        candidates: List[str] = []
        for s in active:
            try:
                full = resolve_scoped_path(path, s, allow)
            except (ValueError, PermissionError):
                continue
            try:
                if await self.client.note_exists(full):
                    candidates.append(full)
            except ObsidianAPIError:
                continue

        if not candidates:
            raise ValueError("Note not found")
        if len(candidates) > 1:
            raise ValueError(
                "The same path exists in more than one workspace; pass scope to disambiguate."
            )

        full_path = candidates[0]
        rel, used_scope = strip_scope_prefix(full_path, allow)
        try:
            content = await self.client.read_note(full_path)
            metadata: Dict[str, Any] = {
                "path": rel,
                "scope": used_scope,
                "content_length": len(content),
            }
            try:
                note_metadata = await self.client.get_note_metadata(full_path)
                metadata.update(
                    {
                        "size": note_metadata.size,
                        "modified": note_metadata.modified.isoformat(),
                        "created": note_metadata.created.isoformat()
                        if note_metadata.created
                        else None,
                        "tags": note_metadata.tags,
                    }
                )
            except Exception:
                pass

            return {
                "content": [
                    {"type": "text", "text": f"# Content of {rel} ({used_scope})\n\n{content}"}
                ],
                "metadata": metadata,
            }

        except ObsidianAPIError as e:
            if e.status_code == 404:
                raise ValueError("Note not found") from e
            raise ValueError(f"Failed to read note: {e.message}") from e

    async def create_note(
        self,
        path: str,
        content: str,
        scope: Optional[str] = None,
        create_folders: bool = True,
        use_template: bool = True,
        template_vars: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """Create a note under a workspace; templates load from that workspace."""
        if not self.client:
            raise ValueError("Obsidian client not initialized. Check OBSIDIAN_API_KEY.")

        try:
            from ..utils.template_utils import template_detector

            original_path = path
            normalized_path = template_detector.normalize_folder_path(path)
            path_was_normalized = original_path != normalized_path
            path = normalized_path

            ctx = get_effective_workspace_context()
            allow = tuple(ctx.allowed_scopes)
            try:
                forbid_scope_prefix_in_agent_path(original_path)
                write_scope = resolve_write_scope(scope, allow)
                full_path = resolve_scoped_path(path, write_scope, allow)
            except (ValueError, PermissionError) as e:
                raise self._access_error(e) from e

            final_content = content
            template_applied = False
            note_type = None
            template_source = "none"

            # Check if user provided content with frontmatter
            # If frontmatter exists, user has structured their content - don't override with templates
            existing_frontmatter, body = template_detector.extract_frontmatter(content)
            user_provided_frontmatter = bool(existing_frontmatter)

            # Apply template if requested and appropriate
            # BUT: NEVER override if user provided their own frontmatter
            # This respects user's explicit content structure
            if use_template and not user_provided_frontmatter:
                note_type = template_detector.detect_note_type_from_path(path)

                # Special handling for meeting notes - smart content building
                if note_type == "meeting-note":
                    # Extract note name from path
                    note_name = (
                        path.split("/")[-1]
                        .replace(".md", "")
                        .replace("-", " ")
                        .title()
                    )

                    # Check if we have structured data via template_vars
                    if template_vars and any(
                        k in template_vars
                        for k in [
                            "attendees",
                            "agenda",
                            "discussion",
                            "action_items",
                            "decisions",
                        ]
                    ):
                        # Build from structured data
                        meeting_data = {
                            "title": template_vars.get("title", note_name),
                            "date": template_vars.get("date", datetime.now().strftime("%Y-%m-%d")),
                            "time": template_vars.get("time", ""),
                            "meeting_type": template_vars.get("meeting_type", ""),
                            "attendees": template_vars.get("attendees", []),
                            "agenda": template_vars.get("agenda", []),
                            "discussion": template_vars.get("discussion", ""),
                            "discussion_points": template_vars.get("discussion_points", []),
                            "action_items": template_vars.get("action_items", []),
                            "decisions": template_vars.get("decisions", []),
                            "follow_up": template_vars.get("follow_up", ""),
                            "notes": template_vars.get("notes", ""),
                            "related_links": template_vars.get("related_links", []),
                        }

                        frontmatter, body = template_detector.build_meeting_note_from_data(**meeting_data)
                        final_content = template_detector.build_content_with_frontmatter(frontmatter, body)
                        template_applied = True
                        template_source = "smart-builder"

                    # Check if content has substantial freeform text - parse it
                    elif content.strip() and len(content.strip()) > 50:
                        # Parse freeform content to extract structured data
                        parsed_data = template_detector.parse_meeting_content(content)

                        # Merge with any template_vars provided
                        if template_vars:
                            parsed_data.update(template_vars)

                        # Add title if not provided
                        if "title" not in parsed_data:
                            parsed_data["title"] = template_vars.get("title", note_name) if template_vars else note_name

                        # Build meeting note from parsed/merged data
                        frontmatter, body = template_detector.build_meeting_note_from_data(**parsed_data)
                        final_content = template_detector.build_content_with_frontmatter(frontmatter, body)
                        template_applied = True
                        template_source = "smart-parser"

                # Only proceed with vault/hardcoded templates if smart builder didn't handle it
                if not template_applied:
                    vault_template_path = template_detector.get_template_path_for_folder(
                        path, workspace_scope=write_scope
                    )

                    if vault_template_path:
                        # Try to read template from vault
                        try:
                            template_content = await self.client.read_note(vault_template_path)

                            # Prepare default template variables
                            note_name = (
                                path.split("/")[-1]
                                .replace(".md", "")
                                .replace("-", " ")
                                .title()
                            )
                            default_vars = {
                                "title": note_name,
                                "date": datetime.now().strftime("%Y-%m-%d"),
                                "datetime": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                "time": datetime.now().strftime("%H:%M"),
                            }

                            # Merge with user-provided template variables
                            if template_vars:
                                default_vars.update(template_vars)

                            # Apply template variable substitution
                            templated_content = template_detector.apply_template(
                                template_content, **default_vars
                            )
                            
                            # Append user's original content to the template
                            # This preserves any content provided even without frontmatter
                            if content.strip():
                                final_content = templated_content + "\n\n" + content.strip()
                            else:
                                final_content = templated_content
                            
                            template_applied = True
                            template_source = "vault"

                        except Exception as template_error:
                            # Fall back to hardcoded templates if vault template fails
                            print(f"Warning: Could not read vault template {vault_template_path}: {template_error}")
                            vault_template_path = None

                    # Fall back to hardcoded templates if no vault template
                    if not vault_template_path or not template_applied:
                        if note_type:
                            # Check if content already has frontmatter
                            existing_frontmatter, body = template_detector.extract_frontmatter(
                                content
                            )

                            if not existing_frontmatter:
                                # Apply default frontmatter for this note type
                                default_frontmatter = template_detector.get_default_frontmatter(
                                    note_type, path
                                )

                                # Use the body content (original content without frontmatter)
                                # If body is empty, use template body
                                if not body.strip():
                                    note_name = (
                                        path.split("/")[-1]
                                        .replace(".md", "")
                                        .replace("-", " ")
                                        .title()
                                    )
                                    body = template_detector.get_default_body_template(
                                        note_type, note_name
                                    )

                                # Build final content with frontmatter + body (preserves original content)
                                final_content = (
                                    template_detector.build_content_with_frontmatter(
                                        default_frontmatter, body
                                    )
                                )
                                template_applied = True
                                template_source = "hardcoded"

            success = await self.client.create_note(full_path, final_content, create_folders)

            if success:
                template_info = ""
                if template_applied:
                    if template_source == "vault":
                        template_info = f"\n🎯 Applied {note_type} template from vault + your content"
                    elif template_source == "smart-builder":
                        template_info = f"\n🎯 Built {note_type} from structured data"
                    elif template_source == "smart-parser":
                        template_info = f"\n🎯 Parsed {note_type} from content"
                    elif template_source == "hardcoded":
                        template_info = f"\n🎯 Applied {note_type} template + your content"
                elif use_template and user_provided_frontmatter:
                    template_info = f"\n📝 Used your content as-is (frontmatter detected)"

                path_info = ""
                if path_was_normalized:
                    path_info = f"\n📍 Path normalized: {original_path} → {path}"

                warnings = _entity_write_warnings(path, final_content)
                warning_info = ""
                if warnings:
                    warning_info = "\n⚠️  " + "\n⚠️  ".join(warnings)

                return {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"✅ Successfully created note: {path} (scope={write_scope})"
                                f"{path_info}{template_info}{warning_info}\n\n"
                                f"Content length: {len(final_content)} characters"
                            ),
                        }
                    ],
                    "metadata": {
                        "path": path,
                        "scope": write_scope,
                        "original_path": original_path if path_was_normalized else path,
                        "path_normalized": path_was_normalized,
                        "content_length": len(final_content),
                        "created_at": datetime.now().isoformat(),
                        "folders_created": create_folders,
                        "template_applied": template_applied,
                        "template_source": template_source,
                        "note_type": note_type,
                        "validation_warnings": warnings,
                    },
                }
            else:
                raise ValueError("Note creation returned False")

        except ObsidianAPIError as e:
            if e.status_code == 409:
                raise ValueError("Note already exists")
            raise ValueError(f"Failed to create note: {e.message}")
        except Exception as e:
            raise ValueError(f"Unexpected error creating note: {str(e)}")

    async def update_note(
        self,
        path: str,
        content: str,
        scope: Optional[str] = None,
        preserve_format: bool = True,
    ) -> Dict[str, Any]:
        """Update note content (scoped)."""
        if not self.client:
            raise ValueError("Obsidian client not initialized. Check OBSIDIAN_API_KEY.")

        try:
            from ..utils.template_utils import template_detector
            import re

            full_path, rel_path, write_scope = self._resolve_note_path_for_write(
                path, scope, normalize=True
            )

            final_content = content
            format_preserved = False
            date_mismatch_warning = ""

            # Check for date mismatch between path and content (for daily notes)
            if "daily-notes" in rel_path or "06_daily-notes" in rel_path:
                # Extract date from path (format: YYYY-MM-DD)
                path_date_match = re.search(r'(\d{4}-\d{2}-\d{2})', rel_path)
                if path_date_match:
                    path_date = path_date_match.group(1)
                    
                    # Extract date from content frontmatter
                    frontmatter, _ = template_detector.extract_frontmatter(content)
                    content_date = None
                    if "creation-date" in frontmatter:
                        content_date_str = str(frontmatter["creation-date"])
                        # Extract YYYY-MM-DD from the date string
                        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', content_date_str)
                        if date_match:
                            content_date = date_match.group(1)
                    
                    # Also check the heading for date
                    heading_match = re.search(r'(\d{4})', content)
                    content_year = heading_match.group(1) if heading_match else None
                    
                    # Warn if dates don't match
                    if content_date and path_date != content_date:
                        date_mismatch_warning = f"\n⚠️  Date mismatch detected: Path has {path_date} but content has {content_date}. Consider updating the path to match the content date."
                    elif content_year and path_date[:4] != content_year:
                        date_mismatch_warning = f"\n⚠️  Year mismatch detected: Path has year {path_date[:4]} but content mentions year {content_year}. Consider updating the path to match the content date."

            # Preserve existing format if requested
            if preserve_format:
                try:
                    existing_content = await self.client.read_note(full_path)
                    note_type = template_detector.detect_note_type_from_path(rel_path)
                    # Entity cards (entities/customer/…, entities/person/…, etc.) are
                    # not in the SPARK folder->type map, so detect returns None and
                    # their hand-maintained frontmatter would be clobbered on update.
                    # Treat any entities/ note as a structure-preserving write.
                    if not note_type and rel_path.replace("\\", "/").startswith("entities/"):
                        note_type = "entity"

                    if note_type:
                        final_content = template_detector.preserve_existing_structure(
                            existing_content, content, note_type
                        )
                        format_preserved = True
                except Exception:
                    pass

            success = await self.client.update_note(full_path, final_content)

            if success:
                format_info = (
                    f"\n🔒 Preserved existing format" if format_preserved else ""
                )

                warnings = _entity_write_warnings(rel_path, final_content)
                warning_info = ""
                if warnings:
                    warning_info = "\n⚠️  " + "\n⚠️  ".join(warnings)

                return {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"✅ Successfully updated note: {rel_path} (scope={write_scope})"
                                f"{format_info}{warning_info}{date_mismatch_warning}\n\n"
                                f"New content length: {len(final_content)} characters"
                            ),
                        }
                    ],
                    "metadata": {
                        "path": rel_path,
                        "scope": write_scope,
                        "content_length": len(final_content),
                        "updated_at": datetime.now().isoformat(),
                        "format_preserved": format_preserved,
                        "validation_warnings": warnings,
                        "date_mismatch_warning": date_mismatch_warning
                        if date_mismatch_warning
                        else None,
                    },
                }
            else:
                raise ValueError("Note update returned False")

        except ObsidianAPIError as e:
            if e.status_code == 404:
                raise ValueError("Note not found")
            raise ValueError(f"Failed to update note: {e.message}")
        except Exception as e:
            raise ValueError(f"Unexpected error updating note: {str(e)}")

    async def append_note(
        self,
        path: str,
        content: str,
        scope: Optional[str] = None,
        separator: str = "\n\n",
    ) -> Dict[str, Any]:
        """Append to a note (scoped)."""
        if not self.client:
            raise ValueError("Obsidian client not initialized. Check OBSIDIAN_API_KEY.")

        try:
            full_path, rel_path, write_scope = self._resolve_note_path_for_write(
                path, scope, normalize=True
            )
            success = await self.client.append_note(full_path, content, separator)

            if success:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"✅ Successfully appended to note: {rel_path} "
                                f"(scope={write_scope})\n\n"
                                f"Appended content length: {len(content)} characters"
                            ),
                        }
                    ],
                    "metadata": {
                        "path": rel_path,
                        "scope": write_scope,
                        "appended_length": len(content),
                        "separator": separator,
                        "appended_at": datetime.now().isoformat(),
                    },
                }
            else:
                raise ValueError("Note append returned False")

        except ObsidianAPIError as e:
            if e.status_code == 404:
                raise ValueError("Note not found")
            raise ValueError(f"Failed to append to note: {e.message}")
        except Exception as e:
            raise ValueError(f"Unexpected error appending to note: {str(e)}")

    async def delete_note(self, path: str, scope: Optional[str] = None) -> Dict[str, Any]:
        """Delete a note (scoped)."""
        if not self.client:
            raise ValueError("Obsidian client not initialized. Check OBSIDIAN_API_KEY.")

        try:
            full_path, rel_path, write_scope = self._resolve_note_path_for_write(
                path, scope, normalize=True
            )
            success = await self.client.delete_note(full_path)

            if success:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"✅ Successfully deleted note: {rel_path} (scope={write_scope})",
                        }
                    ],
                    "metadata": {
                        "path": rel_path,
                        "scope": write_scope,
                        "deleted_at": datetime.now().isoformat(),
                    },
                }
            else:
                raise ValueError("Note deletion returned False")

        except ObsidianAPIError as e:
            if e.status_code == 404:
                raise ValueError("Note not found")
            raise ValueError(f"Failed to delete note: {e.message}")
        except Exception as e:
            raise ValueError(f"Unexpected error deleting note: {str(e)}")

    async def list_notes(
        self,
        folder: str = "",
        scope: Optional[str] = None,
        modified_after: Optional[str] = None,
        modified_before: Optional[str] = None,
        days: Optional[float] = None,
        hours: Optional[float] = None,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """List notes under allowed workspace roots (optional folder, scope, mtime filters)."""
        if not self.client:
            raise ValueError("Obsidian client not initialized. Check OBSIDIAN_API_KEY.")

        if limit is not None and limit < 0:
            raise ValueError("limit must be >= 0")

        ctx = get_effective_workspace_context()
        allow = tuple(ctx.allowed_scopes)
        try:
            active = active_scopes_for_read(scope, allow)
        except (ValueError, PermissionError) as e:
            raise self._access_error(e) from e

        try:
            if folder:
                forbid_scope_prefix_in_agent_path(folder)

            try:
                lower, upper = resolve_list_notes_time_window(
                    modified_after=modified_after,
                    modified_before=modified_before,
                    days=days,
                    hours=hours,
                )
            except ValueError as e:
                raise ValueError(str(e)) from e

            time_or_limit = (
                lower is not None
                or upper is not None
                or days is not None
                or hours is not None
                or limit is not None
            )

            notes_data: List[Dict[str, Any]] = []
            for s in active:
                list_path = scoped_list_folder(folder, s)
                notes = await self.client.list_notes(list_path, include_tags=False)
                for note in notes:
                    if not note_mtime_in_window(note.modified, lower, upper):
                        continue
                    rel, inferred_scope = strip_scope_prefix(note.path, allow)
                    used_scope = inferred_scope or s
                    note_info = {
                        "path": rel,
                        "scope": used_scope,
                        "name": note.name,
                        "size": note.size,
                        "modified": note.modified.isoformat(),
                        "created": note.created.isoformat() if note.created else None,
                        "tags": note.tags or [],
                    }
                    notes_data.append(note_info)

            if time_or_limit:
                notes_data.sort(key=lambda n: n["modified"], reverse=True)
            if limit is not None:
                notes_data = notes_data[:limit]

            response_text = f"Found {len(notes_data)} notes"
            if folder:
                response_text += f" in folder '{folder}'"
            if lower is not None or upper is not None or days is not None or hours is not None:
                response_text += " (mtime filter applied)"
            if limit is not None:
                response_text += f", limit={limit}"
            response_text += ":\n\n"
            for note_info in notes_data:
                response_text += f"📝 **{note_info['name']}** [{note_info['scope']}]\n"
                response_text += f"   Path: {note_info['path']}\n"
                response_text += f"   Size: {note_info['size']:,} bytes\n"
                response_text += (
                    f"   Modified: {note_info['modified'][:16].replace('T', ' ')}\n"
                )
                if note_info["tags"]:
                    response_text += f"   Tags: {', '.join(note_info['tags'])}\n"
                response_text += "\n"

            meta_filters: Dict[str, Any] = {}
            if modified_after is not None:
                meta_filters["modified_after"] = modified_after
            if modified_before is not None:
                meta_filters["modified_before"] = modified_before
            if days is not None:
                meta_filters["days"] = days
            if hours is not None:
                meta_filters["hours"] = hours
            if lower is not None:
                meta_filters["effective_modified_after"] = lower.isoformat()
            if upper is not None:
                meta_filters["effective_modified_before"] = upper.isoformat()
            if limit is not None:
                meta_filters["limit"] = limit

            return {
                "content": [{"type": "text", "text": response_text}],
                "metadata": {
                    "total_notes": len(notes_data),
                    "folder": folder,
                    "notes": notes_data,
                    **meta_filters,
                },
            }

        except ObsidianAPIError as e:
            raise ValueError(f"Failed to list notes: {e.message}")
        except Exception as e:
            raise ValueError(f"Unexpected error listing notes: {str(e)}")

    async def get_vault_structure(
        self, use_cache: bool = True, scope: Optional[str] = None
    ) -> Dict[str, Any]:
        """Folder tree with note counts, limited to allowed workspaces."""
        if not self.client:
            raise ValueError("Obsidian client not initialized. Check OBSIDIAN_API_KEY.")

        ctx = get_effective_workspace_context()
        allow = tuple(ctx.allowed_scopes)
        try:
            active = active_scopes_for_read(scope, allow)
        except (ValueError, PermissionError) as e:
            raise self._access_error(e) from e

        try:
            structure = await self.client.get_vault_structure(
                use_cache=use_cache, include_notes=False
            )

            sorted_src = sorted(structure.folders, key=lambda f: f.path)
            picked: List[Any] = []
            for folder in sorted_src:
                if any(
                    folder.path == s or folder.path.startswith(s + "/") for s in active
                ):
                    picked.append(folder)

            total_notes = 0
            for s in active:
                for folder in structure.folders:
                    if folder.path == s:
                        total_notes += folder.notes_count
                        break

            folders_data: List[Dict[str, Any]] = []
            response_text = "# Vault Structure\n\n"
            response_text += f"**Root:** {structure.root_path}\n"
            response_text += f"**Notes (allowed workspaces):** {total_notes}\n"
            response_text += f"**Folders (filtered):** {len(picked)}\n\n## Folder Structure\n\n"

            for folder in picked:
                rel, sc = strip_scope_prefix(folder.path, allow)
                display_path = rel if rel else folder.name
                depth = display_path.count("/") if display_path else 0
                indent = "  " * depth
                label = f"{display_path}/" if display_path else f"{folder.name}/"
                folder_line = (
                    f"{indent}📁 {label} [{sc}] ({folder.notes_count} notes"
                )
                if folder.subfolders_count > 0:
                    folder_line += f", {folder.subfolders_count} subfolders"
                folder_line += ")\n"
                response_text += folder_line
                folders_data.append(
                    {
                        "path": display_path,
                        "scope": sc,
                        "name": folder.name,
                        "parent": folder.parent,
                        "notes_count": folder.notes_count,
                        "subfolders_count": folder.subfolders_count,
                    }
                )

            return {
                "content": [{"type": "text", "text": response_text}],
                "metadata": {
                    "root_path": structure.root_path,
                    "total_notes": total_notes,
                    "total_folders": len(picked),
                    "folders": folders_data,
                    "cached": use_cache,
                },
            }

        except ObsidianAPIError as e:
            raise ValueError(f"Failed to get vault structure: {e.message}")
        except Exception as e:
            raise ValueError(f"Unexpected error getting vault structure: {str(e)}")

    async def keyword_search(
        self,
        keyword: str,
        folder: str = "",
        case_sensitive: bool = False,
        limit: int = 20,
        scope: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Relevance-ranked keyword search over the parsed corpus (mtime-cached).

        Replaces the previous read-all-notes-over-REST fan-out: the corpus is
        parsed once and cached per file mtime, and matches are ranked with
        title/alias/agent_context/frontmatter hits scored above plain body hits.
        """
        if not keyword.strip():
            raise ValueError("Keyword cannot be empty")

        if folder:
            forbid_scope_prefix_in_agent_path(folder)

        try:
            matching_notes = await self._get_vault_intel().search_notes_ranked(
                keyword,
                scope=scope,
                folder=folder or None,
                limit=limit,
                case_sensitive=case_sensitive,
            )
        except (ValueError, PermissionError) as e:
            raise self._access_error(e) from e
        except Exception as e:
            raise ValueError(f"Keyword search failed: {str(e)}")

        total_found = len(matching_notes)
        results_text = f"# Keyword Search Results\n\n**Query:** {keyword}\n"
        if folder:
            results_text += f"**Folder:** {folder}\n"
        results_text += f"**Total Found:** {total_found}\n"
        results_text += f"**Case Sensitive:** {'Yes' if case_sensitive else 'No'}\n\n"
        if total_found == 0:
            results_text += "No notes found containing the specified keyword.\n"
        else:
            results_text += "## Matching Notes (ranked)\n\n"
            for i, note in enumerate(matching_notes, 1):
                results_text += f"### {i}. {note['name']} [{note['scope']}]\n"
                results_text += f"**Path:** {note['path']}\n"
                if note.get("agent_context"):
                    results_text += f"**Context:** {note['agent_context']}\n"
                results_text += f"**Score:** {note['score']}\n"
                results_text += f"**Match:** {note['context']}\n\n"

        return {
            "content": [{"type": "text", "text": results_text}],
            "metadata": {
                "keyword": keyword,
                "folder": folder,
                "case_sensitive": case_sensitive,
                "total_found": total_found,
                "limit": limit,
                "matching_notes": matching_notes,
            },
        }

    async def check_note_exists(
        self, path: str, scope: Optional[str] = None
    ) -> Dict[str, Any]:
        """Return whether the note exists; disambiguates across workspaces."""
        if not self.client:
            raise ValueError("Obsidian client not initialized. Check OBSIDIAN_API_KEY.")

        ctx = get_effective_workspace_context()
        allow = tuple(ctx.allowed_scopes)
        try:
            forbid_scope_prefix_in_agent_path(path)
            active = active_scopes_for_read(scope, allow)
        except (ValueError, PermissionError) as e:
            raise self._access_error(e) from e

        try:
            hits: List[Dict[str, Any]] = []
            for s in active:
                try:
                    full = resolve_scoped_path(path, s, allow)
                except (ValueError, PermissionError):
                    continue
                if await self.client.note_exists(full):
                    rel, sc = strip_scope_prefix(full, allow)
                    entry: Dict[str, Any] = {"scope": sc or s, "path": rel}
                    try:
                        meta = await self.client.get_note_metadata(full)
                        entry["lastModified"] = meta.modified.isoformat()
                    except Exception:
                        pass
                    hits.append(entry)

            exists = len(hits) > 0
            result: Dict[str, Any] = {"exists": exists, "matches": hits}
            if len(hits) == 1:
                result["scope"] = hits[0]["scope"]
                result["path"] = hits[0]["path"]
                if "lastModified" in hits[0]:
                    result["lastModified"] = hits[0]["lastModified"]

            text = f"Note '{path}' {'exists' if exists else 'does not exist'}"
            if len(hits) > 1:
                text += f" ({len(hits)} workspaces; specify scope to narrow)"
            elif exists and hits:
                text += f" (scope={hits[0]['scope']})"

            return {
                "content": [{"type": "text", "text": text}],
                "metadata": result,
            }
        except Exception as e:
            raise ValueError(f"Failed to check note existence: {str(e)}")

    async def list_journal(
        self,
        startDate: str,
        endDate: str,
        scope: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Daily notes in range, tagged by workspace; deduplicated by (scope, date)."""
        if not self.client:
            raise ValueError("Obsidian client not initialized. Check OBSIDIAN_API_KEY.")

        ctx = get_effective_workspace_context()
        allow = tuple(ctx.allowed_scopes)
        try:
            active = active_scopes_for_read(scope, allow)
        except (ValueError, PermissionError) as e:
            raise self._access_error(e) from e

        try:
            try:
                start = datetime.strptime(startDate, "%Y-%m-%d")
                end = datetime.strptime(endDate, "%Y-%m-%d")
            except ValueError as e:
                raise ValueError(
                    f"Invalid date format. Expected YYYY-MM-DD: {str(e)}"
                ) from e
            if start > end:
                raise ValueError("startDate must be before or equal to endDate")

            date_pattern = re.compile(r"(\d{4}-\d{2}-\d{2})")
            seen: set = set()
            entries: List[Dict[str, Any]] = []

            for s in active:
                for daily_root in ("06_daily-notes", "daily-notes", "journal"):
                    folder = f"{s}/{daily_root}"
                    try:
                        notes = await self.client.list_notes(folder, include_tags=False)
                    except ObsidianAPIError:
                        continue
                    for note in notes:
                        date_match = date_pattern.search(note.name)
                        if not date_match:
                            continue
                        note_date_str = date_match.group(1)
                        try:
                            note_date = datetime.strptime(note_date_str, "%Y-%m-%d")
                        except ValueError:
                            continue
                        if not (start <= note_date <= end):
                            continue
                        key = (s, note_date_str)
                        if key in seen:
                            continue
                        seen.add(key)
                        rel, _ = strip_scope_prefix(note.path, allow)
                        entries.append(
                            {
                                "date": note_date_str,
                                "filename": note.name,
                                "path": rel,
                                "scope": s,
                            }
                        )

            entries.sort(key=lambda x: (x["date"], x["scope"]))
            lines = [f"- {e['date']} [{e['scope']}] {e['path']}" for e in entries]
            body = (
                "\n".join(lines)
                if lines
                else "No daily notes found in the specified date range."
            )

            return {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"Found {len(entries)} daily notes between {startDate} "
                            f"and {endDate}:\n\n{body}"
                        ),
                    }
                ],
                "metadata": {
                    "startDate": startDate,
                    "endDate": endDate,
                    "notes": entries,
                },
            }
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Failed to list daily notes: {str(e)}")

    async def list_daily_notes(
        self,
        startDate: str,
        endDate: str,
        scope: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Alias of list_journal."""
        return await self.list_journal(startDate, endDate, scope=scope)

    # =================== Vault Intelligence Tools ===================

    async def resolve_entity(
        self, name: str, scope: Optional[str] = None
    ) -> Dict[str, Any]:
        return await self._get_vault_intel().resolve_entity(name, scope=scope)

    async def query_frontmatter(
        self,
        filters: Dict[str, Any],
        scope: Optional[str] = None,
        folder: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await self._get_vault_intel().query_frontmatter(
            filters, scope=scope, folder=folder, tag=tag
        )

    async def get_dossier(
        self,
        name: str,
        scope: Optional[str] = None,
        depth: int = 1,
    ) -> Dict[str, Any]:
        return await self._get_vault_intel().get_dossier(name, scope=scope, depth=depth)

    async def lint_vault(
        self,
        scope: Optional[str] = None,
        folder: Optional[str] = None,
        fix: bool = False,
    ) -> Dict[str, Any]:
        return await self._get_vault_intel().lint_vault(
            scope=scope, folder=folder, fix=fix
        )

    # =================== Tool Dispatcher ===================

    async def capture_seed(
        self,
        title: str = "",
        content: str = "",
        source: str = "",
        capture_type: str = "thought",
        spark: str = "",
        captured: str = "",
    ) -> Dict[str, Any]:
        """Write a quick-capture note to the root 01_seeds/ inbox.

        Emits the canonical capture schema documented in
        passion/07_blueprints/proj-capture-system.md (type: capture, status: inbox).
        The format is driven by a vault-managed template at
        00_system/templates/capture.md (variables: title, content, source, captured,
        spark, capture_type, agent_context); an inline schema is used as a fallback
        if that template is unavailable. Captures stay deliberately distinct from
        `type: seed` so they stay out of ontology seed queries until they are
        promoted into a scope at weekly triage.
        """
        if not self.client:
            raise ValueError("Obsidian client not initialized. Check OBSIDIAN_API_KEY.")

        try:
            import re as _re
            from ..utils.template_utils import template_detector

            # Vault-managed capture template (same pattern create_note uses for
            # scoped notes). Lives at the vault root so it stays out of the
            # 01_seeds/ Dataview inbox query.
            capture_template_path = "00_system/templates/capture.md"

            # Normalize capture_type to the three supported pipelines
            capture_type = (capture_type or "thought").strip().lower()
            if capture_type not in ("thought", "post", "excerpt"):
                capture_type = "thought"

            # Spark is the "why saved" line — mandatory for post/excerpt (a naked
            # item is useless in three weeks), optional for self-justifying thoughts.
            spark = (spark or "").strip()
            if capture_type in ("post", "excerpt") and not spark:
                raise ValueError(
                    f"'spark' (one-line why) is required for capture_type='{capture_type}'"
                )

            # Resolve the capture timestamp (default: now), kept second-precision ISO.
            now = datetime.now()
            captured = (captured or "").strip()
            if captured:
                captured_iso = captured
                try:
                    stamp = datetime.fromisoformat(captured)
                except ValueError:
                    stamp = now
            else:
                captured_iso = now.strftime("%Y-%m-%dT%H:%M:%S")
                stamp = now

            date_str = stamp.strftime("%Y-%m-%d")
            time_str = stamp.strftime("%H%M")

            # Filename: YYYY-MM-DD_HHmm_<short-kebab>.md (datetime-prefixed to avoid
            # rapid-capture collisions). Slug from title, falling back to the body.
            slug_source = title.strip() or content.strip() or capture_type
            slug = _re.sub(r"[^a-z0-9]+", "-", slug_source.lower()).strip("-")[:48]
            if not slug:
                slug = capture_type
            filename = f"{date_str}_{time_str}_{slug}.md"
            vault_path = f"01_seeds/{filename}"

            # Short orientation line for triage. Escape quotes to keep YAML valid.
            context_seed = (title.strip() or content.strip()).replace("\n", " ").strip()
            agent_context = context_seed[:120].replace('"', "'")
            if not agent_context:
                agent_context = f"Capture ({capture_type}) awaiting triage."

            # Human-friendly heading for the note body. Falls back to a trimmed
            # context line, then a generic label, so the H1 is never blank.
            title_resolved = (
                title.strip() or context_seed[:80].strip() or f"Capture ({capture_type})"
            )

            # Sanitize values bound for quoted YAML so a stray quote can't break
            # the frontmatter.
            spark_safe = spark.replace('"', "'")
            source_safe = (source or "unspecified").replace('"', "'")
            body = content.strip()

            template_vars = {
                "capture_type": capture_type,
                "source": source_safe,
                "captured": captured_iso,
                "spark": spark_safe,
                "agent_context": agent_context,
                "title": title_resolved,
                "content": body,
            }

            # Prefer the vault-managed capture template so the format lives in one
            # editable place (consistent with create_note). Fall back to the inline
            # schema if the template can't be read, so a capture never fails just
            # because the template file is missing or not yet deployed.
            final_content = None
            try:
                template_content = await self.client.read_note(capture_template_path)
                final_content = (
                    template_detector.apply_template(template_content, **template_vars).rstrip()
                    + "\n"
                )
            except Exception as template_error:
                print(
                    f"Warning: capture template {capture_template_path} unavailable, "
                    f"using inline schema: {template_error}"
                )

            if not final_content:
                # Inline fallback — same schema + body shape as the vault template.
                frontmatter = "\n".join(
                    [
                        "---",
                        "type: capture",
                        f"capture_type: {capture_type}",
                        f'source: "{source_safe}"',
                        f"captured: {captured_iso}",
                        f'spark: "{spark_safe}"',
                        "status: inbox",
                        "target_scope:",
                        f'agent_context: "{agent_context}"',
                        "tags: [capture, inbox]",
                        "---",
                    ]
                )
                final_content = (
                    f"{frontmatter}\n\n# {title_resolved}\n\n"
                    f"## Idea\n\n{body}\n\n## Why It Matters\n\n"
                    + (f"{spark_safe}\n" if spark_safe else "")
                )

            success = await self.client.create_note(vault_path, final_content, True)
            if not success:
                raise ValueError("Note creation returned False")

            return {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"✅ Captured to 01_seeds/{filename}\n\n"
                            f"Type: capture ({capture_type})\n"
                            f"Source: {source or 'unspecified'}\n"
                            f"Status: inbox (awaiting triage)"
                        ),
                    }
                ],
                "metadata": {
                    "path": vault_path,
                    "filename": filename,
                    "title": title,
                    "capture_type": capture_type,
                    "source": source,
                    "spark": spark,
                    "status": "inbox",
                    "captured": captured_iso,
                    "created_at": now.isoformat(),
                },
            }

        except ObsidianAPIError as e:
            if e.status_code == 409:
                raise ValueError("A capture with this name already exists for this minute")
            raise ValueError(f"Failed to write capture: {e.message}")
        except Exception as e:
            raise ValueError(f"Unexpected error writing capture: {str(e)}")

    async def create_event(
        self,
        event_type: str,
        event_date: str = "",
        title: str = "",
        customer: str = "",
        organizations: Optional[List[str]] = None,
        participants: Optional[List[str]] = None,
        concepts: Optional[List[str]] = None,
        agent_context: str = "",
        outcome: str = "",
        source_note: str = "",
        poc_stage: str = "",
        scope: Optional[str] = None,
        update_backrefs: bool = True,
    ) -> Dict[str, Any]:
        """Create a schema-valid event entity card and (optionally) its back-refs."""
        if not self.client:
            raise ValueError("Obsidian client not initialized. Check OBSIDIAN_API_KEY.")

        HOME_ORGS = {"make", "make-company", "celonis", "celonis-company"}

        event_type = (event_type or "").strip().lower()
        if event_type not in EVENT_TYPES:
            raise ValueError(
                f"event_type '{event_type}' is not in the controlled vocabulary "
                f"{sorted(EVENT_TYPES)}"
            )

        event_date = (event_date or "").strip() or datetime.now().strftime("%Y-%m-%d")
        try:
            datetime.strptime(event_date, "%Y-%m-%d")
        except ValueError as e:
            raise ValueError("event_date must be YYYY-MM-DD") from e

        def slugify(value: str) -> str:
            return re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")

        customer = (customer or "").strip()
        cust_slug = slugify(customer) if customer else ""
        org_slugs = [slugify(o) for o in (organizations or []) if str(o).strip()]
        part_slugs = [slugify(p) for p in (participants or []) if str(p).strip()]
        concept_slugs = [slugify(c) for c in (concepts or []) if str(c).strip()]
        # Every event involves the home org; default organizations to make.
        if not org_slugs:
            org_slugs = ["make"]

        fn_slug = cust_slug or org_slugs[0]

        ctx = get_effective_workspace_context()
        allow = tuple(ctx.allowed_scopes)
        try:
            write_scope = resolve_write_scope(scope, allow)
        except (ValueError, PermissionError) as e:
            raise self._access_error(e) from e

        base = f"entities/event/{event_date}-{fn_slug}-{event_type}"
        rel = f"{base}.md"
        n = 1
        while True:
            full = resolve_scoped_path(rel, write_scope, allow)
            if not await self.client.note_exists(full):
                break
            n += 1
            rel = f"{base}-{n}.md"
        event_stem = Path(rel).stem

        display_subject = customer or org_slugs[0]
        title = title.strip() or (
            f"{display_subject.replace('-', ' ').title()} "
            f"{event_type.replace('-', ' ').title()}"
        )
        agent_context = agent_context.strip() or (
            f"{event_type.replace('-', ' ')} on {event_date}"
            + (f" with {customer}" if customer else "")
        )
        ac_safe = agent_context.replace('"', "'")

        fm_lines = [
            "---",
            "entity_type: event",
            f"event_type: {event_type}",
            f"event_date: {event_date}",
            "aliases: []",
        ]
        if cust_slug:
            fm_lines.append(f'customer: "[[{cust_slug}]]"')
        fm_lines.append("organizations:")
        fm_lines.extend(f'  - "[[{o}]]"' for o in org_slugs)
        fm_lines.append("participants:")
        fm_lines.extend(f'  - "[[{p}]]"' for p in part_slugs)
        fm_lines.append("concepts:")
        fm_lines.extend(f'  - "[[{c}]]"' for c in concept_slugs)
        if source_note.strip():
            sn = source_note.strip()
            if not sn.startswith("[["):
                sn = f"[[{sn}]]"
            fm_lines.append(f'source_note: "{sn}"')
        if poc_stage.strip():
            fm_lines.append(f"poc_stage: {poc_stage.strip()}")
        fm_lines.append(f"last_updated: {datetime.now().strftime('%Y-%m-%d')}")
        fm_lines.append("source_count: 1")
        fm_lines.append(f'agent_context: "{ac_safe}"')
        fm_lines.append("---")

        body_lines = [f"# {title}", "", f"> agent_context: {agent_context}", "", "## Connections"]
        if cust_slug:
            body_lines.append(f"- [[{cust_slug}]] - customer")
        body_lines.extend(f"- [[{p}]] - participant" for p in part_slugs)
        body_lines.extend(f"- [[{c}]] - concept" for c in concept_slugs)
        if not (cust_slug or part_slugs or concept_slugs):
            body_lines.append("- [[entity]] - related")
        body_lines += ["", "## Outcome", f"- {outcome.strip() or 'TBD'}", ""]

        content = "\n".join(fm_lines) + "\n\n" + "\n".join(body_lines)

        await self.create_note(
            path=rel,
            content=content,
            scope=write_scope,
            create_folders=True,
            use_template=False,
        )

        backref_results: List[Dict[str, str]] = []
        if update_backrefs:
            vi = self._get_vault_intel()
            corpus_notes = vi.corpus.load_scope([write_scope], include_sections=False)
            name_index = vi.corpus.index_by_name(corpus_notes)
            targets: List[str] = []
            if cust_slug:
                targets.append(cust_slug)
            targets.extend(part_slugs)
            targets.extend(o for o in org_slugs if o not in HOME_ORGS)

            seen: set = set()
            changed_any = False
            for slug in targets:
                if slug in seen:
                    continue
                seen.add(slug)
                note = name_index.get(slug)
                if note is None:
                    backref_results.append({"entity": slug, "status": "unresolved"})
                    continue
                target_full = f"{write_scope}/{note.path}"
                try:
                    existing = await self.client.read_note(target_full)
                    updated, changed = _upsert_events_section(
                        existing, event_stem, event_type, event_date
                    )
                    if changed:
                        await self.client.update_note(target_full, updated)
                        changed_any = True
                        backref_results.append(
                            {"entity": note.path, "status": "updated"}
                        )
                    else:
                        backref_results.append(
                            {"entity": note.path, "status": "already-linked"}
                        )
                except Exception as e:  # best-effort; never fail the event create
                    backref_results.append(
                        {"entity": note.path, "status": f"error: {e}"}
                    )
            if changed_any:
                vi.corpus.clear_cache()

        backref_summary = ""
        if update_backrefs:
            updated_n = sum(1 for r in backref_results if r["status"] == "updated")
            backref_summary = f"\nBack-refs updated: {updated_n}/{len(backref_results)}"

        return {
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"✅ Created event: {rel} (scope={write_scope})\n"
                        f"event_type={event_type}, event_date={event_date}"
                        f"{backref_summary}"
                    ),
                }
            ],
            "metadata": {
                "path": rel,
                "scope": write_scope,
                "event_stem": event_stem,
                "event_type": event_type,
                "event_date": event_date,
                "customer": cust_slug,
                "organizations": org_slugs,
                "participants": part_slugs,
                "concepts": concept_slugs,
                "backrefs_updated": update_backrefs,
                "backref_results": backref_results,
                "created_at": datetime.now().isoformat(),
            },
        }

    async def execute_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Dispatch MCP tool call by registered tool name."""
        args = dict(arguments or {})
        handler_name = OBSIDIAN_TOOL_DISPATCH.get(tool_name)
        if handler_name is None:
            raise ValueError(f"Unknown tool: {tool_name}")

        method = getattr(self, handler_name)

        try:
            return await method(**args)
        except TypeError as e:
            raise ValueError(f"Invalid arguments for tool '{tool_name}': {str(e)}")
        except Exception as e:
            raise ValueError(f"Tool '{tool_name}' failed: {str(e)}")


# Global instance
obsidian_tools = ObsidianTools()
