"""
Obsidian Resources Implementation for MCP Protocol
Handles browseable vault structure via obsidian://notes/{path} URI patterns
"""
import asyncio
import urllib.parse
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from ..types import MCPResource
from ..obsidian_client import ObsidianClient, ObsidianAPIError


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
    Manages MCP Resources for Obsidian vault access
    Implements browseable vault structure via URI patterns
    """

    def __init__(self, obsidian_client: ObsidianClient):
        self.client = obsidian_client
        self.resource_cache: Dict[str, Tuple[ResourceContent, datetime]] = {}
        self.cache_ttl = timedelta(minutes=5)  # Match vault structure cache
        self.uri_scheme = "obsidian"
        self.uri_authority = "notes"

    # =================== URI Pattern Processing ===================

    def parse_uri(self, uri: str) -> Tuple[str, str]:
        """
        Parse obsidian://notes/{path} URI into components

        Args:
            uri: Resource URI (e.g., "obsidian://notes/daily/2024-01-15.md")

        Returns:
            Tuple of (scheme_authority, path)

        Raises:
            ValueError: If URI format is invalid
        """
        if not uri.startswith(f"{self.uri_scheme}://"):
            raise ValueError(
                f"Invalid URI scheme. Expected '{self.uri_scheme}://', got: {uri}"
            )

        # Remove scheme
        without_scheme = uri[len(f"{self.uri_scheme}://") :]

        # Split authority and path
        parts = without_scheme.split("/", 1)
        authority = parts[0]
        path = parts[1] if len(parts) > 1 else ""

        if authority != self.uri_authority:
            raise ValueError(
                f"Invalid URI authority. Expected '{self.uri_authority}', got: {authority}"
            )

        # URL decode the path
        path = urllib.parse.unquote(path)

        return f"{self.uri_scheme}://{authority}", path

    def build_uri(self, path: str) -> str:
        """
        Build obsidian://notes/{path} URI from path

        Args:
            path: Vault path (e.g., "daily/2024-01-15.md")

        Returns:
            Complete URI
        """
        # URL encode the path
        encoded_path = urllib.parse.quote(path, safe="/")
        return f"{self.uri_scheme}://{self.uri_authority}/{encoded_path}"

    def is_folder_path(self, path: str) -> bool:
        """
        Determine if path represents a folder (ends with / or has no extension)
        """
        if not path or path.endswith("/"):
            return True

        # Check if path has file extension
        import os

        _, ext = os.path.splitext(path)
        return not ext

    # =================== Resource Discovery ===================

    async def discover_resources(self) -> List[MCPResource]:
        """
        Discover all available resources from vault structure

        Returns:
            List of MCPResource objects for browseable access
        """
        resources = []

        try:
            # Add vault root resource
            resources.append(
                MCPResource(
                    uri=f"{self.uri_scheme}://{self.uri_authority}/",
                    name="Vault Root",
                    description="Browse all notes and folders in the vault",
                    mimeType="application/json",
                )
            )

            # Get vault structure
            vault_structure = await self.client.get_vault_structure(use_cache=True)

            # Add folder resources
            for folder in vault_structure.folders:
                folder_path = folder.path.rstrip("/") + "/"
                resources.append(
                    MCPResource(
                        uri=self.build_uri(folder_path),
                        name=folder.name,
                        description=f"Folder with {folder.notes_count} notes and {folder.subfolders_count} subfolders",
                        mimeType="application/json",
                    )
                )

            # Add note resources
            for note in vault_structure.notes:
                resources.append(
                    MCPResource(
                        uri=self.build_uri(note.path),
                        name=note.name,
                        description=f"Note ({note.size} bytes, modified {note.modified.strftime('%Y-%m-%d')})",
                        mimeType="text/markdown",
                    )
                )

        except Exception as e:
            # If vault discovery fails, at least provide root resource
            print(f"Warning: Resource discovery failed: {e}")
            if not resources:  # Only add if we don't have vault root already
                resources.append(
                    MCPResource(
                        uri=f"{self.uri_scheme}://{self.uri_authority}/",
                        name="Vault Root",
                        description="Vault access (limited due to connection issues)",
                        mimeType="application/json",
                    )
                )

        return resources

    # =================== Resource Content Reading ===================

    async def read_resource(self, uri: str) -> ResourceContent:
        """
        Read content of a specific resource

        Args:
            uri: Resource URI to read

        Returns:
            ResourceContent with the resource data

        Raises:
            ValueError: If URI is invalid
            ObsidianAPIError: If resource cannot be accessed
        """
        # Check cache first
        if uri in self.resource_cache:
            content, cached_time = self.resource_cache[uri]
            if datetime.now() - cached_time < self.cache_ttl:
                return content

        # Parse URI
        scheme_authority, path = self.parse_uri(uri)

        # Handle different resource types
        if self.is_folder_path(path):
            content = await self._read_folder_resource(uri, path)
        else:
            content = await self._read_note_resource(uri, path)

        # Cache the result
        self.resource_cache[uri] = (content, datetime.now())

        return content

    async def _read_folder_resource(self, uri: str, path: str) -> ResourceContent:
        """Read folder resource (returns JSON listing)"""
        try:
            if not path or path == "/":
                # Vault root - list all top-level items
                vault_structure = await self.client.get_vault_structure(use_cache=True)

                items = []

                # Add folders
                for folder in vault_structure.folders:
                    if "/" not in folder.path.strip("/"):  # Top-level folders only
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

                # Add top-level notes
                for note in vault_structure.notes:
                    if "/" not in note.path:  # Top-level notes only
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

                content_data = {
                    "folder_path": path or "/",
                    "total_items": len(items),
                    "folders": [item for item in items if item["type"] == "folder"],
                    "notes": [item for item in items if item["type"] == "note"],
                }

            else:
                # Specific folder - list contents
                folder_path = path.rstrip("/")
                folder_contents = await self.client.get_folder_contents(folder_path)

                items = []

                # Process subfolders
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

                # Process notes
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

            import json

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

        except Exception as e:
            raise ObsidianAPIError(f"Failed to read folder resource {uri}: {str(e)}")

    async def _read_note_resource(self, uri: str, path: str) -> ResourceContent:
        """Read note resource (returns markdown content)"""
        try:
            # Read note content
            note_content = await self.client.read_note(path)

            # Get note metadata
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
                # Fallback if metadata fails
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
        """
        Invalidate resource cache

        Args:
            uri_pattern: Optional pattern to match URIs for selective invalidation
        """
        if uri_pattern is None:
            # Clear all cache
            self.resource_cache.clear()
        else:
            # Clear matching URIs
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
            "cache_hit_ratio": "N/A",  # Would need hit/miss tracking
            "cache_ttl_minutes": self.cache_ttl.total_seconds() / 60,
        }


# Global instance to be used by MCP server
obsidian_resources: Optional[ObsidianResources] = None


def get_obsidian_resources() -> ObsidianResources:
    """Get or create the global ObsidianResources instance"""
    global obsidian_resources

    if obsidian_resources is None:
        from ..obsidian_client import ObsidianClient

        client = ObsidianClient()
        obsidian_resources = ObsidianResources(client)

    return obsidian_resources
