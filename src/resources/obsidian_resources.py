"""
Obsidian Resources Implementation for MCP Protocol
Handles browseable vault access via obsidian://notes/{path} URI patterns.

resources/list exposes a tiny curated set: vault root, allowed workspace roots,
and optional root pins (AGENTS.md / index.md / CLAUDE.md). Deep paths use
resources/read, RFC 6570 templates, or scoped MCP tools.

Both list and read enforce API-key workspace scope (same ContextVar as tools).
Future MCP Apps UI bundles use the ui:// scheme (see list_ui_resources).
"""
from __future__ import annotations

import asyncio
import json
import os
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..clients.obsidian_client import ObsidianAPIError, ObsidianClient
from ..scope import KNOWN_SCOPES, get_effective_workspace_context
from ..types import MCPResource, MCPResourceTemplate


# Root-level docs agents/apps may pin without a path template.
CURATED_ROOT_PINS: Tuple[str, ...] = ("AGENTS.md", "index.md", "CLAUDE.md")

UI_MIME_TYPE = "text/html;profile=mcp-app"


@dataclass
class ResourceContent:
    """Content of a resource with metadata"""

    uri: str
    mimeType: str
    text: Optional[str] = None
    blob: Optional[bytes] = None
    metadata: Optional[Dict[str, Any]] = None


class ObsidianResources:
    """
    Manages MCP Resources for Obsidian vault access.
    List = workspace roots + pins; read = any allowed path; templates for deep URIs.
    """

    def __init__(self, obsidian_client: ObsidianClient):
        self.client = obsidian_client
        self.resource_cache: Dict[str, Tuple[ResourceContent, datetime]] = {}
        self.cache_ttl = timedelta(minutes=5)
        self.uri_scheme = "obsidian"
        self.uri_authority = "notes"
        self.ui_scheme = "ui"
        self.ui_authority = "ziksaka"

    # =================== URI Pattern Processing ===================

    def parse_uri(self, uri: str) -> Tuple[str, str]:
        """
        Parse obsidian://notes/{path} URI into (scheme_authority, path).
        """
        if not uri.startswith(f"{self.uri_scheme}://"):
            raise ValueError(
                f"Invalid URI scheme. Expected '{self.uri_scheme}://', got: {uri}"
            )

        without_scheme = uri[len(f"{self.uri_scheme}://") :]
        parts = without_scheme.split("/", 1)
        authority = parts[0]
        path = parts[1] if len(parts) > 1 else ""

        if authority != self.uri_authority:
            raise ValueError(
                f"Invalid URI authority. Expected '{self.uri_authority}', got: {authority}"
            )

        path = urllib.parse.unquote(path)
        return f"{self.uri_scheme}://{authority}", path

    def build_uri(self, path: str) -> str:
        """Build obsidian://notes/{path} URI from vault-relative path."""
        encoded_path = urllib.parse.quote(path, safe="/")
        return f"{self.uri_scheme}://{self.uri_authority}/{encoded_path}"

    def _allowed_scopes(self) -> Tuple[str, ...]:
        return tuple(get_effective_workspace_context().allowed_scopes)

    def _assert_path_allowed(self, path: str) -> None:
        """Enforce API-key workspace scope for resource reads."""
        allowed = self._allowed_scopes()
        cleaned = (path or "").strip("/")
        if not cleaned:
            return
        first = cleaned.split("/")[0]
        if first in KNOWN_SCOPES:
            if first not in allowed:
                raise PermissionError(f"Access denied to workspace `{first}`")
            return
        if cleaned in CURATED_ROOT_PINS:
            return
        raise PermissionError(f"Access denied to resource path `{cleaned}`")

    def is_folder_path(self, path: str) -> bool:
        """True if path represents a folder (ends with / or has no extension)."""
        if not path or path.endswith("/"):
            return True
        _, ext = os.path.splitext(path)
        return not ext

    # =================== Resource Discovery ===================

    async def discover_resources(self) -> List[MCPResource]:
        """
        List vault root + allowed workspace roots + curated root pins.

        No full vault walk. Deep notes/folders are reached via resources/read,
        templates, or scoped tools. Results respect the current API-key scopes.
        """
        allowed = self._allowed_scopes()
        vault_root = Path(self.client.vault_path)
        resources: List[MCPResource] = [
            MCPResource(
                uri=f"{self.uri_scheme}://{self.uri_authority}/",
                name="Vault Root",
                description=(
                    "Top-level vault browse (scope-filtered). Workspace roots for "
                    f"this key: {', '.join(allowed) or '(none)'}. Notes are not "
                    "enumerated—use resources/read with obsidian://notes/{+path}, "
                    "or scoped tools (list_notes/read_note/search)."
                ),
                mimeType="application/json",
            )
        ]

        for scope in KNOWN_SCOPES:
            if scope not in allowed:
                continue
            scope_dir = vault_root / scope
            if not scope_dir.is_dir():
                continue
            resources.append(
                MCPResource(
                    uri=self.build_uri(f"{scope}/"),
                    name=scope,
                    description=(
                        f"Workspace `{scope}` root. Read for a folder listing; "
                        "use tools or path templates for notes inside."
                    ),
                    mimeType="application/json",
                )
            )

        for pin in CURATED_ROOT_PINS:
            pin_path = vault_root / pin
            if pin_path.is_file():
                resources.append(
                    MCPResource(
                        uri=self.build_uri(pin),
                        name=pin,
                        description=f"Vault root pin · {pin}",
                        mimeType="text/markdown",
                    )
                )

        resources.extend(self.list_ui_resources())
        return resources

    def list_resource_templates(self) -> List[MCPResourceTemplate]:
        """RFC 6570 URI templates for paths not present in resources/list."""
        base = f"{self.uri_scheme}://{self.uri_authority}"
        return [
            MCPResourceTemplate(
                uriTemplate=f"{base}/{{+path}}",
                name="Vault note or folder",
                description=(
                    "Any vault-relative note or folder, e.g. work/entities/customer/gojob.md. "
                    "Prefixed with workspace (personal/passion/work). Scope-filtered on read."
                ),
            ),
            MCPResourceTemplate(
                uriTemplate=f"{base}/{{scope}}/06_daily-notes/{{date}}.md",
                name="Daily note",
                description=(
                    "Daily journal note. scope=personal|passion|work; date=YYYY-MM-DD. "
                    "Prefer list_journal / read_note tools when scripting."
                ),
            ),
            MCPResourceTemplate(
                uriTemplate=f"{base}/work/entities/{{type}}/{{slug}}.md",
                name="Work entity card",
                description=(
                    "Work entity note under entities/{type}/{slug}.md "
                    "(e.g. customer/gojob). Prefer resolve_entity / get_dossier tools."
                ),
            ),
        ]

    def list_ui_resources(self) -> List[MCPResource]:
        """
        MCP Apps UI bundles (ui://ziksaka/...).

        Delegates to src.apps.registry so HTML bundles on disk are discoverable.
        Tools reference these via ``_meta.ui.resourceUri``.
        """
        try:
            from ..apps.registry import list_ui_app_resources

            return list_ui_app_resources()
        except Exception as e:
            print(f"Warning: Could not list UI resources: {e}")
            return []

    def build_ui_uri(self, app_path: str) -> str:
        """Build ui://ziksaka/{app_path} for MCP App bundles."""
        encoded = urllib.parse.quote(app_path.strip("/"), safe="/")
        return f"{self.ui_scheme}://{self.ui_authority}/{encoded}"

    # =================== Resource Content Reading ===================

    async def read_resource(self, uri: str) -> ResourceContent:
        """Read a resource URI (obsidian://notes/… or ui://ziksaka/…)."""
        if uri.startswith(f"{self.ui_scheme}://"):
            from ..apps.registry import read_ui_app_resource

            data = await asyncio.to_thread(read_ui_app_resource, uri)
            return ResourceContent(
                uri=data["uri"],
                mimeType=data["mimeType"],
                text=data.get("text"),
                metadata=data.get("metadata"),
            )

        if uri in self.resource_cache:
            content, cached_time = self.resource_cache[uri]
            if datetime.now() - cached_time < self.cache_ttl:
                _, cached_path = self.parse_uri(uri)
                self._assert_path_allowed(cached_path)
                return content

        _, path = self.parse_uri(uri)
        self._assert_path_allowed(path)

        if self.is_folder_path(path):
            content = await self._read_folder_resource(uri, path)
        elif (path or "").strip("/") in CURATED_ROOT_PINS:
            content = await self._read_root_pin(uri, path.strip("/"))
        else:
            content = await self._read_note_resource(uri, path)

        self.resource_cache[uri] = (content, datetime.now())
        return content

    async def _read_root_pin(self, uri: str, pin: str) -> ResourceContent:
        """Read a vault-root curated pin (not scope-prefixed)."""
        full = Path(self.client.vault_path) / pin

        def _load() -> Tuple[str, int, float]:
            text = full.read_text(encoding="utf-8")
            stat = full.stat()
            return text, stat.st_size, stat.st_mtime

        try:
            text, size, mtime = await asyncio.to_thread(_load)
        except FileNotFoundError:
            raise ObsidianAPIError(f"Note not found: {pin}", 404)
        except OSError as e:
            raise ObsidianAPIError(f"Failed to read root pin {pin}: {e}")

        return ResourceContent(
            uri=uri,
            mimeType="text/markdown",
            text=text,
            metadata={
                "resource_type": "note",
                "path": pin,
                "size": size,
                "modified": datetime.fromtimestamp(mtime).isoformat(),
            },
        )

    async def _read_folder_resource(self, uri: str, path: str) -> ResourceContent:
        """Read folder resource (returns JSON listing), scope-filtered."""
        try:
            allowed = self._allowed_scopes()
            if not path or path == "/":
                vault_structure = await self.client.get_vault_structure(
                    use_cache=True, include_notes=True
                )
                items: List[Dict[str, Any]] = []

                for folder in vault_structure.folders:
                    if "/" not in folder.path.strip("/"):
                        if folder.name not in allowed:
                            continue
                        items.append(
                            {
                                "type": "folder",
                                "name": folder.name,
                                "path": folder.path,
                                "uri": self.build_uri(folder.path.rstrip("/") + "/"),
                                "notes_count": folder.notes_count,
                                "subfolders_count": folder.subfolders_count,
                            }
                        )

                for note in vault_structure.notes:
                    if "/" not in note.path and note.path in CURATED_ROOT_PINS:
                        items.append(
                            {
                                "type": "note",
                                "name": note.name,
                                "path": note.path,
                                "uri": self.build_uri(note.path),
                                "size": note.size,
                                "modified": note.modified.isoformat(),
                                "tags": note.tags or [],
                            }
                        )

                # Workspace roots that exist but have no notes yet still appear
                vault_root = Path(self.client.vault_path)
                listed = {i["path"].rstrip("/") for i in items if i["type"] == "folder"}
                for scope in allowed:
                    if scope in listed:
                        continue
                    if (vault_root / scope).is_dir():
                        items.append(
                            {
                                "type": "folder",
                                "name": scope,
                                "path": scope,
                                "uri": self.build_uri(f"{scope}/"),
                                "notes_count": 0,
                                "subfolders_count": 0,
                            }
                        )

                content_data = {
                    "folder_path": path or "/",
                    "total_items": len(items),
                    "folders": [item for item in items if item["type"] == "folder"],
                    "notes": [item for item in items if item["type"] == "note"],
                }
            else:
                folder_path = path.rstrip("/")
                folder_contents = await self.client.get_folder_contents(folder_path)
                items = []

                for folder in folder_contents.get("subfolders", []):
                    items.append(
                        {
                            "type": "folder",
                            "name": folder.get("name", ""),
                            "path": folder.get("path", ""),
                            "uri": self.build_uri(
                                folder.get("path", "").rstrip("/") + "/"
                            ),
                        }
                    )

                for note in folder_contents.get("notes", []):
                    items.append(
                        {
                            "type": "note",
                            "name": note.get("name", ""),
                            "path": note.get("path", ""),
                            "uri": self.build_uri(note.get("path", "")),
                            "size": note.get("size", 0),
                        }
                    )

                content_data = {
                    "folder_path": folder_path,
                    "total_items": len(items),
                    "folders": [item for item in items if item["type"] == "folder"],
                    "notes": [item for item in items if item["type"] == "note"],
                }

            return ResourceContent(
                uri=uri,
                mimeType="application/json",
                text=json.dumps(content_data, indent=2),
                metadata={
                    "resource_type": "folder",
                    "item_count": content_data["total_items"],
                    "generated_at": datetime.now().isoformat(),
                },
            )

        except PermissionError:
            raise
        except Exception as e:
            raise ObsidianAPIError(f"Failed to read folder resource {uri}: {str(e)}")

    async def _read_note_resource(self, uri: str, path: str) -> ResourceContent:
        """Read note resource (returns markdown content)."""
        try:
            note_content = await self.client.read_note(path)

            try:
                note_metadata = await self.client.get_note_metadata(path)
                metadata = {
                    "resource_type": "note",
                    "size": note_metadata.size,
                    "modified": note_metadata.modified.isoformat(),
                    "created": note_metadata.created.isoformat()
                    if note_metadata.created
                    else None,
                    "tags": note_metadata.tags or [],
                    "path": path,
                }
            except Exception:
                metadata = {
                    "resource_type": "note",
                    "path": path,
                    "content_length": len(note_content),
                }

            return ResourceContent(
                uri=uri, mimeType="text/markdown", text=note_content, metadata=metadata
            )

        except ObsidianAPIError as e:
            if e.status_code == 404:
                raise ObsidianAPIError(f"Note not found: {path}", 404)
            raise
        except Exception as e:
            raise ObsidianAPIError(f"Failed to read note resource {uri}: {str(e)}")

    # =================== Cache Management ===================

    def invalidate_cache(self, uri_pattern: Optional[str] = None):
        """Invalidate resource content cache."""
        if uri_pattern is None:
            self.resource_cache.clear()
        else:
            keys_to_remove = [
                uri for uri in self.resource_cache.keys() if uri_pattern in uri
            ]
            for key in keys_to_remove:
                del self.resource_cache[key]

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        now = datetime.now()
        total_entries = len(self.resource_cache)
        expired_entries = sum(
            1
            for _, cached_time in self.resource_cache.values()
            if now - cached_time >= self.cache_ttl
        )

        return {
            "total_entries": total_entries,
            "expired_entries": expired_entries,
            "cache_hit_ratio": "N/A",
            "cache_ttl_minutes": self.cache_ttl.total_seconds() / 60,
        }


# Global instance to be used by MCP server
obsidian_resources: Optional[ObsidianResources] = None


def get_obsidian_resources() -> ObsidianResources:
    """Get or create the global ObsidianResources instance"""
    global obsidian_resources

    if obsidian_resources is None:
        from ..clients.obsidian_client import ObsidianClient

        client = ObsidianClient()
        obsidian_resources = ObsidianResources(client)

    return obsidian_resources
