"""
Obsidian MCP Tools Implementation
Workspace-scoped vault tools using ObsidianClient
"""
import json
import os
import re
import asyncio
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
from ..types import MCPTool


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


class ObsidianTools:
    """Workspace-scoped Obsidian MCP tools."""

    def __init__(self):
        self.client = None
        self._initialize_client()

    def _initialize_client(self):
        """Initialize ObsidianClient with error handling"""
        try:
            self.client = ObsidianClient()
        except ValueError as e:
            # Client will be None if API key is not set
            print(f"Warning: ObsidianClient not initialized: {e}")
            self.client = None

    def get_tools(self) -> List[MCPTool]:
        """Register canonical tool names and obs_* aliases (transition period)."""

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
                "List workspace folders (scopes) allowed for the current API key.",
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
                "obs_get_vault_structure",
                "Alias of vault_structure.",
                vault_props,
                [],
            ),
            _tool(
                "list_notes",
                "List notes with metadata (scoped).",
                list_props,
                [],
            ),
            _tool("obs_list_notes", "Alias of list_notes.", list_props, []),
            _tool(
                "list_journal",
                "Daily notes in a date range with workspace tags (deduplicated).",
                journal_props,
                ["startDate", "endDate"],
            ),
            _tool(
                "obs_list_daily_notes",
                "Alias of list_journal.",
                journal_props,
                ["startDate", "endDate"],
            ),
            _tool(
                "search",
                "Keyword search in note contents (scoped).",
                search_props,
                ["keyword"],
            ),
            _tool(
                "obs_keyword_search",
                "Alias of search.",
                search_props,
                ["keyword"],
            ),
            _tool(
                "read_note",
                "Read a note (scoped path).",
                read_path_prop,
                ["path"],
            ),
            _tool("obs_read_note", "Alias of read_note.", read_path_prop, ["path"]),
            _tool(
                "create_note",
                "Create a note in a workspace (scope required if key has multiple workspaces).",
                create_props,
                ["path", "content"],
            ),
            _tool(
                "obs_create_note",
                "Alias of create_note.",
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
                "obs_update_note",
                "Alias of update_note.",
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
                "obs_append_note",
                "Alias of append_note.",
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
                "obs_check_note_exists",
                "Alias of note_exists.",
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
                "obs_delete_note",
                "Alias of delete_note.",
                delete_props,
                ["path"],
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

                return {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"✅ Successfully created note: {path} (scope={write_scope})"
                                f"{path_info}{template_info}\n\n"
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

                return {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"✅ Successfully updated note: {rel_path} (scope={write_scope})"
                                f"{format_info}{date_mismatch_warning}\n\n"
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
        self, folder: str = "", scope: Optional[str] = None
    ) -> Dict[str, Any]:
        """List notes under allowed workspace roots (optional folder + scope)."""
        if not self.client:
            raise ValueError("Obsidian client not initialized. Check OBSIDIAN_API_KEY.")

        ctx = get_effective_workspace_context()
        allow = tuple(ctx.allowed_scopes)
        try:
            active = active_scopes_for_read(scope, allow)
        except (ValueError, PermissionError) as e:
            raise self._access_error(e) from e

        try:
            if folder:
                forbid_scope_prefix_in_agent_path(folder)

            notes_data: List[Dict[str, Any]] = []
            for s in active:
                list_path = scoped_list_folder(folder, s)
                notes = await self.client.list_notes(list_path, include_tags=False)
                for note in notes:
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

            response_text = f"Found {len(notes_data)} notes"
            if folder:
                response_text += f" in folder '{folder}'"
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

            return {
                "content": [{"type": "text", "text": response_text}],
                "metadata": {
                    "total_notes": len(notes_data),
                    "folder": folder,
                    "notes": notes_data,
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
        """Keyword search across allowed workspaces."""
        if not self.client:
            raise ValueError("Obsidian client not initialized. Check OBSIDIAN_API_KEY.")

        if not keyword.strip():
            raise ValueError("Keyword cannot be empty")

        ctx = get_effective_workspace_context()
        allow = tuple(ctx.allowed_scopes)
        try:
            active = active_scopes_for_read(scope, allow)
        except (ValueError, PermissionError) as e:
            raise self._access_error(e) from e

        try:
            if folder:
                forbid_scope_prefix_in_agent_path(folder)

            all_notes: List[tuple] = []
            for s in active:
                lp = scoped_list_folder(folder, s)
                part = await self.client.list_notes(lp, include_tags=False)
                for note in part:
                    all_notes.append((s, note))

            if not all_notes:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": "No notes found in the selected workspace(s).",
                        }
                    ],
                    "metadata": {
                        "keyword": keyword,
                        "folder": folder,
                        "case_sensitive": case_sensitive,
                        "total_found": 0,
                        "limit": limit,
                        "matching_notes": [],
                    },
                }

            matching_notes: List[Dict[str, Any]] = []
            search_keyword = keyword if case_sensitive else keyword.lower()
            batch_size = 15

            async def search_in_note(
                scope_key: str, note
            ) -> Optional[Dict[str, Any]]:
                try:
                    content = await self.client.read_note(note.path)
                    search_content = content if case_sensitive else content.lower()
                    if search_keyword not in search_content:
                        return None
                    rel, inferred = strip_scope_prefix(note.path, allow)
                    used_scope = inferred or scope_key
                    context = self._extract_context(content, keyword, case_sensitive)
                    return {
                        "path": rel,
                        "scope": used_scope,
                        "name": note.name,
                        "size": note.size,
                        "modified": note.modified.isoformat(),
                        "context": context,
                        "folder": os.path.dirname(rel) if rel else "",
                    }
                except Exception:
                    return None

            for i in range(0, len(all_notes), batch_size):
                if len(matching_notes) >= limit:
                    break
                batch = all_notes[i : i + batch_size]
                results = await asyncio.gather(
                    *[search_in_note(s, note) for s, note in batch],
                    return_exceptions=True,
                )
                for result in results:
                    if result and not isinstance(result, Exception):
                        matching_notes.append(result)
                        if len(matching_notes) >= limit:
                            break

            matching_notes.sort(key=lambda x: x["modified"], reverse=True)
            total_found = len(matching_notes)
            results_text = f"# Keyword Search Results\n\n**Query:** {keyword}\n"
            if folder:
                results_text += f"**Folder:** {folder}\n"
            results_text += f"**Total Found:** {total_found}\n"
            results_text += (
                f"**Case Sensitive:** {'Yes' if case_sensitive else 'No'}\n\n"
            )
            if total_found == 0:
                results_text += "No notes found containing the specified keyword.\n"
            else:
                results_text += "## Matching Notes\n\n"
                for i, note in enumerate(matching_notes, 1):
                    results_text += f"### {i}. {note['name']} [{note['scope']}]\n"
                    results_text += f"**Path:** {note['path']}\n"
                    results_text += f"**Folder:** {note['folder']}\n"
                    results_text += f"**Size:** {note['size']} bytes\n"
                    results_text += f"**Modified:** {note['modified']}\n"
                    results_text += f"**Context:** {note['context']}\n\n"

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

        except Exception as e:
            raise ValueError(f"Keyword search failed: {str(e)}")

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

    def _extract_context(
        self, content: str, keyword: str, case_sensitive: bool = False
    ) -> str:
        """Extract context around the keyword in the content"""
        search_content = content if case_sensitive else content.lower()
        search_keyword = keyword if case_sensitive else keyword.lower()

        # Find the first occurrence of the keyword
        index = search_content.find(search_keyword)
        if index == -1:
            return "Keyword not found"

        # Extract context (50 characters before and after)
        start = max(0, index - 50)
        end = min(len(content), index + len(keyword) + 50)

        context = content[start:end].strip()

        # Add ellipsis if we truncated
        if start > 0:
            context = "..." + context
        if end < len(content):
            context = context + "..."

        return context

    # =================== Tool Dispatcher ===================

    async def execute_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Dispatch MCP tool call (canonical names and obs_* aliases)."""
        args = dict(arguments or {})
        tool_methods = {
            "workspaces": self.tool_workspaces,
            "vault_structure": self.get_vault_structure,
            "obs_get_vault_structure": self.get_vault_structure,
            "list_notes": self.list_notes,
            "obs_list_notes": self.list_notes,
            "list_journal": self.list_journal,
            "obs_list_daily_notes": self.list_journal,
            "search": self.keyword_search,
            "obs_keyword_search": self.keyword_search,
            "read_note": self.read_note,
            "obs_read_note": self.read_note,
            "create_note": self.create_note,
            "obs_create_note": self.create_note,
            "update_note": self.update_note,
            "obs_update_note": self.update_note,
            "append_note": self.append_note,
            "obs_append_note": self.append_note,
            "note_exists": self.check_note_exists,
            "obs_check_note_exists": self.check_note_exists,
            "delete_note": self.delete_note,
            "obs_delete_note": self.delete_note,
        }

        if tool_name not in tool_methods:
            raise ValueError(f"Unknown tool: {tool_name}")

        method = tool_methods[tool_name]

        try:
            return await method(**args)
        except TypeError as e:
            raise ValueError(f"Invalid arguments for tool '{tool_name}': {str(e)}")
        except Exception as e:
            raise ValueError(f"Tool '{tool_name}' failed: {str(e)}")


OBSIDIAN_ROUTED_TOOL_NAMES = frozenset(
    {
        "workspaces",
        "vault_structure",
        "obs_get_vault_structure",
        "list_notes",
        "obs_list_notes",
        "list_journal",
        "obs_list_daily_notes",
        "search",
        "obs_keyword_search",
        "read_note",
        "obs_read_note",
        "create_note",
        "obs_create_note",
        "update_note",
        "obs_update_note",
        "append_note",
        "obs_append_note",
        "note_exists",
        "obs_check_note_exists",
        "delete_note",
        "obs_delete_note",
    }
)

# Global instance
obsidian_tools = ObsidianTools()
