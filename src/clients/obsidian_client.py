"""
Obsidian REST API Client Wrapper
Enhanced with full CRUD operations and vault management
"""
import httpx
import json
import urllib.parse
import os
import glob
import asyncio
from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass
from datetime import datetime
import re


@dataclass
class NoteMetadata:
    """Note metadata structure"""

    path: str
    name: str
    size: int
    modified: datetime
    created: Optional[datetime] = None
    tags: Optional[List[str]] = None


@dataclass
class FolderInfo:
    """Folder information structure"""

    path: str
    name: str
    parent: Optional[str]
    notes_count: int = 0
    subfolders_count: int = 0


@dataclass
class VaultStructure:
    """Vault structure representation"""

    root_path: str
    folders: List[FolderInfo]
    notes: List[NoteMetadata]
    total_notes: int
    total_folders: int


class ObsidianAPIError(Exception):
    """Custom exception for Obsidian API errors"""

    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class ObsidianClient:
    """
    Enhanced Obsidian REST API client with full CRUD operations
    """

    def __init__(self):
        self.api_url = os.getenv("OBSIDIAN_API_URL", "http://localhost:36961")
        self.api_key = os.getenv("OBSIDIAN_API_KEY")
        self.vault_path = os.getenv("OBSIDIAN_VAULT_PATH", "")

        if not self.api_key:
            raise ValueError("OBSIDIAN_API_KEY environment variable is required")

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Alternative headers to try if Bearer fails
        self.alt_headers = [
            {"Authorization": self.api_key, "Content-Type": "application/json"},
            {"x-api-key": self.api_key, "Content-Type": "application/json"},
            {"X-API-Key": self.api_key, "Content-Type": "application/json"},
            {"API-Key": self.api_key, "Content-Type": "application/json"},
        ]

        # Cache for vault structure
        self._vault_structure_cache: Optional[VaultStructure] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl = 300  # 5 minutes

        # Cache for filesystem scan (independent of vault structure)
        self._filesystem_notes_cache: Optional[List[NoteMetadata]] = None
        self._filesystem_cache_timestamp: Optional[datetime] = None
        self._filesystem_cache_ttl = 180  # 3 minutes (shorter than vault structure)

    # =================== Basic Vault Operations ===================

    def _discover_notes_filesystem(self, include_tags: bool = False, use_cache: bool = True) -> List[NoteMetadata]:
        """
        Discover all notes in the vault using filesystem scanning
        This is a fallback when the REST API doesn't provide file listings

        Args:
            include_tags: Whether to read file content to extract tags (expensive!)
            use_cache: Whether to use cached results if available
        """
        # Check cache first
        if use_cache and self._filesystem_notes_cache and self._filesystem_cache_timestamp:
            cache_age = (datetime.now() - self._filesystem_cache_timestamp).total_seconds()
            if cache_age < self._filesystem_cache_ttl:
                # If cache has tags but we don't need them, or cache matches our needs, return it
                if not include_tags or (self._filesystem_notes_cache and self._filesystem_notes_cache[0].tags is not None):
                    return self._filesystem_notes_cache

        notes = []
        if not self.vault_path or not os.path.exists(self.vault_path):
            return notes

        try:
            # Find all .md files recursively
            md_pattern = os.path.join(self.vault_path, "**", "*.md")
            md_files = glob.glob(md_pattern, recursive=True)

            for file_path in md_files:
                try:
                    # Get relative path from vault root
                    rel_path = os.path.relpath(file_path, self.vault_path)
                    # Convert Windows paths to forward slashes
                    rel_path = rel_path.replace(os.sep, "/")

                    # Get file stats
                    stat = os.stat(file_path)
                    file_size = stat.st_size
                    modified_time = datetime.fromtimestamp(stat.st_mtime)
                    created_time = datetime.fromtimestamp(stat.st_ctime)

                    # Extract tags ONLY if requested (lazy-loading optimization)
                    tags = None
                    if include_tags:
                        try:
                            with open(file_path, "r", encoding="utf-8") as f:
                                content = f.read(
                                    500
                                )  # Read first 500 chars for frontmatter
                                tags = self._extract_tags(content)
                        except:
                            pass  # Ignore read errors

                    note = NoteMetadata(
                        path=rel_path,
                        name=os.path.basename(file_path),
                        size=file_size,
                        modified=modified_time,
                        created=created_time,
                        tags=tags,
                    )
                    notes.append(note)

                except Exception as e:
                    # Skip files that can't be processed
                    continue

        except Exception as e:
            print(f"Warning: Could not scan filesystem for notes: {e}")

        # Cache the results
        self._filesystem_notes_cache = notes
        self._filesystem_cache_timestamp = datetime.now()

        return notes

    async def get_vault_info(self) -> Dict[str, Any]:
        """Get vault information"""
        async with httpx.AsyncClient(verify=False) as client:
            # Try Bearer token first
            try:
                response = await client.get(
                    f"{self.api_url}/vault/", headers=self.headers, timeout=10.0
                )
                response.raise_for_status()

                # Handle empty response from Obsidian API
                if not response.content:
                    return {
                        "name": "Unknown Vault",
                        "path": self.vault_path,
                        "status": "connected",
                    }

                return response.json()
            except httpx.HTTPStatusError as e:
                print(
                    f"🔍 HTTP Error: Status {e.response.status_code}, Response: {e.response.text}"
                )
                if e.response.status_code in [401, 403]:
                    # Try alternative authentication methods
                    for i, alt_headers in enumerate(self.alt_headers):
                        try:
                            print(
                                f"🔄 Trying auth method {i+1}: {list(alt_headers.keys())[0]}"
                            )
                            response = await client.get(
                                f"{self.api_url}/vault/",
                                headers=alt_headers,
                                timeout=10.0,
                            )
                            response.raise_for_status()
                            print(
                                f"✅ Authentication successful with method {i+1}: {list(alt_headers.keys())[0]}"
                            )

                            # Update headers for future requests
                            self.headers = alt_headers

                            if not response.content:
                                return {
                                    "name": "Unknown Vault",
                                    "path": self.vault_path,
                                    "status": "connected",
                                    "auth_method": list(alt_headers.keys())[0],
                                }
                            return response.json()
                        except httpx.HTTPStatusError as alt_e:
                            print(
                                f"❌ Auth method {i+1} failed: Status {alt_e.response.status_code}"
                            )
                            continue

                raise ObsidianAPIError(
                    f"Failed to get vault info: {e.response.text}",
                    e.response.status_code,
                )
            except Exception as e:
                raise ObsidianAPIError(f"Connection error: {str(e)}")

    async def health_check(self) -> bool:
        """Check if Obsidian REST API is accessible"""
        try:
            await self.get_vault_info()
            return True
        except Exception:
            return False

    # =================== Note Reading Operations ===================

    async def read_note(self, path: str) -> str:
        """
        Read note content by path

        Args:
            path: Note path relative to vault root (e.g., "Daily Notes/2024-01-01.md")

        Returns:
            Note content as string
        """
        if not path:
            raise ValueError("Note path cannot be empty")

        # Ensure path doesn't start with /
        path = path.lstrip("/")

        try:
            async with httpx.AsyncClient(verify=False) as client:
                # URL encode the path to handle special characters
                encoded_path = urllib.parse.quote(path, safe="/")
                response = await client.get(
                    f"{self.api_url}/vault/{encoded_path}",
                    headers=self.headers,
                    timeout=15.0,
                )
                response.raise_for_status()
                return response.text
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ObsidianAPIError(f"Note not found: {path}", 404)
            raise ObsidianAPIError(
                f"Failed to read note {path}: {e.response.text}", e.response.status_code
            )
        except Exception as e:
            raise ObsidianAPIError(f"Connection error reading {path}: {str(e)}")

    async def get_note_metadata(self, path: str) -> NoteMetadata:
        """Get note metadata including size, dates, etc."""
        try:
            # Get file list to find metadata
            files = await self.list_files()

            for file_info in files:
                if file_info.get("path") == path:
                    return NoteMetadata(
                        path=file_info["path"],
                        name=file_info["name"],
                        size=file_info.get("stat", {}).get("size", 0),
                        modified=datetime.fromtimestamp(
                            file_info.get("stat", {}).get("mtime", 0) / 1000
                        ),
                        created=datetime.fromtimestamp(
                            file_info.get("stat", {}).get("ctime", 0) / 1000
                        )
                        if file_info.get("stat", {}).get("ctime")
                        else None,
                    )

            raise ObsidianAPIError(f"Note metadata not found: {path}", 404)
        except Exception as e:
            if isinstance(e, ObsidianAPIError):
                raise
            raise ObsidianAPIError(f"Failed to get note metadata: {str(e)}")

    # =================== Note Writing Operations ===================

    async def create_note(
        self, path: str, content: str, create_folders: bool = True
    ) -> bool:
        """
        Create a new note

        Args:
            path: Note path relative to vault root
            content: Note content
            create_folders: Whether to create parent folders if they don't exist

        Returns:
            True if successful
        """
        if not path:
            raise ValueError("Note path cannot be empty")

        # Ensure path doesn't start with /
        path = path.lstrip("/")

        # Check if note already exists
        try:
            await self.read_note(path)
            raise ObsidianAPIError(f"Note already exists: {path}", 409)
        except ObsidianAPIError as e:
            if e.status_code != 404:  # If it's not "not found", re-raise
                raise

        return await self._write_note(path, content, create_folders)

    async def update_note(self, path: str, content: str) -> bool:
        """
        Update existing note content

        Args:
            path: Note path relative to vault root
            content: New note content

        Returns:
            True if successful
        """
        if not path:
            raise ValueError("Note path cannot be empty")

        # Ensure note exists
        await self.read_note(path)  # Will raise error if not found

        return await self._write_note(path, content, create_folders=False)

    async def append_note(
        self, path: str, content: str, separator: str = "\n\n"
    ) -> bool:
        """
        Append content to existing note

        Args:
            path: Note path relative to vault root
            content: Content to append
            separator: Separator between existing and new content

        Returns:
            True if successful
        """
        if not path:
            raise ValueError("Note path cannot be empty")

        # Read existing content
        existing_content = await self.read_note(path)

        # Append new content
        new_content = existing_content + separator + content

        return await self._write_note(path, new_content, create_folders=False)

    async def delete_note(self, path: str) -> bool:
        """
        Delete a note

        Args:
            path: Note path relative to vault root

        Returns:
            True if successful
        """
        if not path:
            raise ValueError("Note path cannot be empty")

        # Ensure path doesn't start with /
        path = path.lstrip("/")

        try:
            async with httpx.AsyncClient(verify=False) as client:
                encoded_path = urllib.parse.quote(path, safe="/")
                response = await client.delete(
                    f"{self.api_url}/vault/{encoded_path}",
                    headers=self.headers,
                    timeout=10.0,
                )
                response.raise_for_status()
                return True
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ObsidianAPIError(f"Note not found: {path}", 404)
            raise ObsidianAPIError(
                f"Failed to delete note {path}: {e.response.text}",
                e.response.status_code,
            )
        except Exception as e:
            raise ObsidianAPIError(f"Connection error deleting {path}: {str(e)}")

    async def _write_note(
        self, path: str, content: str, create_folders: bool = True
    ) -> bool:
        """Internal method to write note content"""
        path = path.lstrip("/")

        try:
            async with httpx.AsyncClient(verify=False) as client:
                encoded_path = urllib.parse.quote(path, safe="/")

                # Prepare headers for plain text content
                headers = self.headers.copy()
                headers["Content-Type"] = "text/plain; charset=utf-8"

                # Add query parameter for folder creation if needed
                url = f"{self.api_url}/vault/{encoded_path}"
                if create_folders:
                    url += "?createDirectories=true"

                response = await client.put(
                    url,
                    headers=headers,
                    content=content.encode("utf-8"),
                    timeout=15.0,
                )
                response.raise_for_status()
                return True
        except httpx.HTTPStatusError as e:
            raise ObsidianAPIError(
                f"Failed to write note {path}: {e.response.text}",
                e.response.status_code,
            )
        except Exception as e:
            raise ObsidianAPIError(f"Connection error writing {path}: {str(e)}")

    # =================== Search Operations ===================

    async def search_notes(
        self, query: str, folder: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search notes in vault with optional folder filtering

        Args:
            query: Search query string
            folder: Optional folder to limit search scope

        Returns:
            List of search results with note paths and snippets
        """
        if not query.strip():
            raise ValueError("Search query cannot be empty")

        try:
            async with httpx.AsyncClient(verify=False) as client:
                search_data = {"query": query}
                if folder:
                    search_data["folder"] = folder.lstrip("/")

                response = await client.post(
                    f"{self.api_url}/search/simple/",
                    headers=self.headers,
                    json=search_data,
                    timeout=15.0,
                )
                response.raise_for_status()

                # Handle empty response from Obsidian API
                if not response.content:
                    return []  # Return empty results if API returns nothing

                results = response.json()

                # Enhance results with metadata if available
                # Use concurrent fetching for better performance
                async def fetch_metadata_for_result(result):
                    enhanced_result = dict(result)
                    try:
                        # Add metadata if possible
                        metadata = await self.get_note_metadata(result.get("path", ""))
                        enhanced_result["metadata"] = {
                            "size": metadata.size,
                            "modified": metadata.modified.isoformat(),
                            "created": metadata.created.isoformat()
                            if metadata.created
                            else None,
                        }
                    except Exception:
                        # If metadata fails, continue without it
                        pass
                    return enhanced_result

                # Fetch all metadata concurrently using asyncio.gather
                # Use return_exceptions=True to handle individual failures gracefully
                enhanced_results = await asyncio.gather(
                    *[fetch_metadata_for_result(result) for result in results],
                    return_exceptions=True
                )

                # Filter out any exceptions and return valid results
                valid_results = [
                    result for result in enhanced_results
                    if not isinstance(result, Exception)
                ]

                return valid_results
        except httpx.HTTPStatusError as e:
            raise ObsidianAPIError(
                f"Search failed: {e.response.text}", e.response.status_code
            )
        except Exception as e:
            if isinstance(e, ObsidianAPIError):
                raise
            raise ObsidianAPIError(f"Search error: {str(e)}")

    # =================== File and Folder Listing ===================

    async def list_files(self, folder: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List files in vault or specific folder

        Note: This is a simplified implementation that works with available Obsidian REST API endpoints.
        Since /files/ endpoint doesn't exist, we'll return folder structure from vault info.

        Args:
            folder: Optional folder path to list (None for all files)

        Returns:
            List of file information dictionaries
        """
        try:
            # Get vault info to start with folder structure
            vault_info = await self.get_vault_info()
            files = []

            # If we have folders in vault info, add them
            if "files" in vault_info and isinstance(vault_info["files"], list):
                # This contains folder names from vault root
                for item in vault_info["files"]:
                    if isinstance(item, str):
                        # Add as folder
                        files.append(
                            {
                                "path": item.rstrip("/"),
                                "name": item.rstrip("/").split("/")[-1],
                                "type": "folder",
                                "size": 0,
                            }
                        )

            # Filter by folder if specified
            if folder:
                folder = folder.strip("/")
                filtered_files = []
                for file in files:
                    file_path = file.get("path", "")
                    if (
                        folder == ""
                        or file_path.startswith(folder + "/")
                        or file_path == folder
                    ):
                        filtered_files.append(file)
                return filtered_files

            return files

        except Exception as e:
            # Fallback: return empty list if we can't list files
            print(f"Warning: Could not list files: {e}")
            return []

    async def list_notes(self, folder: Optional[str] = None, include_tags: bool = False) -> List[NoteMetadata]:
        """
        List notes with metadata

        Args:
            folder: Optional folder to filter by
            include_tags: Whether to extract tags from notes (expensive - use only when needed)

        Returns:
            List of NoteMetadata objects
        """
        # Use filesystem discovery for better note detection
        # By default, don't extract tags (lazy-loading optimization)
        all_notes = self._discover_notes_filesystem(include_tags=include_tags, use_cache=True)

        # Filter by folder if specified
        if folder:
            folder = folder.strip("/")
            filtered_notes = []
            for note in all_notes:
                note_folder = os.path.dirname(note.path)
                if note_folder == folder or note_folder.startswith(folder + "/"):
                    filtered_notes.append(note)
            return filtered_notes

        return all_notes

    def _extract_tags(self, content: str) -> List[str]:
        """Extract tags from note content"""
        tags = set()

        # Extract from frontmatter
        if content.startswith("---"):
            try:
                end_idx = content.find("---", 3)
                if end_idx > 0:
                    frontmatter = content[3:end_idx]
                    # Simple tag extraction from frontmatter
                    for line in frontmatter.split("\n"):
                        if line.strip().startswith("tags:"):
                            tag_line = line.split(":", 1)[1].strip()
                            if tag_line.startswith("[") and tag_line.endswith("]"):
                                # Array format: tags: [tag1, tag2]
                                tag_list = tag_line[1:-1].split(",")
                                tags.update(
                                    tag.strip().strip("\"'") for tag in tag_list
                                )
                            else:
                                # Simple format: tags: tag1, tag2
                                tags.update(tag.strip() for tag in tag_line.split(","))
            except Exception:
                pass

        # Extract inline tags (#tag)
        inline_tags = re.findall(r"#([a-zA-Z0-9_/-]+)", content)
        tags.update(inline_tags)

        return list(tags)

    # =================== Vault Structure Operations ===================

    async def get_vault_structure(self, use_cache: bool = True) -> VaultStructure:
        """
        Get complete vault structure with folders and notes

        Args:
            use_cache: Whether to use cached structure if available

        Returns:
            VaultStructure object containing complete vault organization
        """
        # Check cache
        if use_cache and self._vault_structure_cache and self._cache_timestamp:
            cache_age = (datetime.now() - self._cache_timestamp).total_seconds()
            if cache_age < self._cache_ttl:
                return self._vault_structure_cache

        try:
            # Get all files (folders from vault info)
            all_files = await self.list_files()

            # Separate folders and notes
            folders = {}  # path -> FolderInfo
            notes = []

            # First, discover all notes using filesystem scanning
            # This is more reliable than the REST API for file discovery
            # Don't include tags by default for better performance
            filesystem_notes = self._discover_notes_filesystem(include_tags=False, use_cache=use_cache)
            notes.extend(filesystem_notes)

            # Process files to build structure
            for file_info in all_files:
                file_path = file_info.get("path", "")
                file_name = file_info.get("name", "")
                file_type = file_info.get("type", "")

                # Handle folders directly from vault info
                if file_type == "folder":
                    folders[file_path] = FolderInfo(
                        path=file_path,
                        name=file_name,
                        parent=None,  # These are root-level folders
                        notes_count=0,  # Will be updated later
                        subfolders_count=0,  # Will be updated later
                    )

                    # Try to find some notes in this folder
                    try:
                        await self._discover_notes_in_folder(file_path, notes)
                    except Exception:
                        # Ignore errors in note discovery
                        pass

                # Handle notes (if we got any from file listings)
                if file_path.endswith((".md", ".txt")):
                    try:
                        stat = file_info.get("stat", {})
                        note = NoteMetadata(
                            path=file_path,
                            name=file_name,
                            size=stat.get("size", 0),
                            modified=datetime.fromtimestamp(stat.get("mtime", 0) / 1000)
                            if stat.get("mtime")
                            else datetime.now(),
                            created=datetime.fromtimestamp(stat.get("ctime", 0) / 1000)
                            if stat.get("ctime")
                            else None,
                        )
                        notes.append(note)
                    except Exception:
                        continue

            # Count notes and subfolders for each folder
            for folder_path, folder_info in folders.items():
                # Count notes in this folder
                folder_info.notes_count = sum(
                    1
                    for note in notes
                    if note.path.startswith(folder_path + "/")
                    and "/" not in note.path[len(folder_path) + 1 :]
                )

                # Count direct subfolders
                folder_info.subfolders_count = sum(
                    1
                    for other_path in folders.keys()
                    if other_path.startswith(folder_path + "/")
                    and "/" not in other_path[len(folder_path) + 1 :]
                )

            # Create vault structure
            vault_info = await self.get_vault_info()
            structure = VaultStructure(
                root_path=vault_info.get("path", self.vault_path),
                folders=list(folders.values()),
                notes=notes,
                total_notes=len(notes),
                total_folders=len(folders),
            )

            # Cache the result
            self._vault_structure_cache = structure
            self._cache_timestamp = datetime.now()

            return structure

        except Exception as e:
            if isinstance(e, ObsidianAPIError):
                raise
            raise ObsidianAPIError(f"Failed to get vault structure: {str(e)}")

    async def get_folder_contents(self, folder_path: str) -> Dict[str, Any]:
        """
        Get contents of a specific folder

        Args:
            folder_path: Path to folder

        Returns:
            Dictionary with folder contents and metadata
        """
        folder_path = folder_path.strip("/")

        try:
            structure = await self.get_vault_structure()

            # Find the folder
            folder_info = None
            for folder in structure.folders:
                if folder.path == folder_path:
                    folder_info = folder
                    break

            if not folder_info and folder_path != "":
                raise ObsidianAPIError(f"Folder not found: {folder_path}", 404)

            # Get notes in this folder
            folder_notes = [
                note
                for note in structure.notes
                if (folder_path == "" and "/" not in note.path)
                or (
                    folder_path != ""
                    and note.path.startswith(folder_path + "/")
                    and "/" not in note.path[len(folder_path) + 1 :]
                )
            ]

            # Get subfolders
            subfolders = [
                folder for folder in structure.folders if folder.parent == folder_path
            ]

            return {
                "folder": folder_info.__dict__
                if folder_info
                else {"path": "", "name": "Root", "parent": None},
                "notes": [note.__dict__ for note in folder_notes],
                "subfolders": [folder.__dict__ for folder in subfolders],
                "total_notes": len(folder_notes),
                "total_subfolders": len(subfolders),
            }

        except Exception as e:
            if isinstance(e, ObsidianAPIError):
                raise
            raise ObsidianAPIError(f"Failed to get folder contents: {str(e)}")

    def invalidate_cache(self):
        """Invalidate the vault structure cache and filesystem cache"""
        self._vault_structure_cache = None
        self._cache_timestamp = None
        self._filesystem_notes_cache = None
        self._filesystem_cache_timestamp = None

    # =================== Obsidian Command Execution ===================

    async def execute_command(self, command: str, **kwargs) -> Dict[str, Any]:
        """
        Execute Obsidian command via REST API

        Args:
            command: Command name to execute
            **kwargs: Command parameters

        Returns:
            Command execution result
        """
        if not command:
            raise ValueError("Command cannot be empty")

        try:
            async with httpx.AsyncClient(verify=False) as client:
                command_data = {"command": command, "parameters": kwargs}

                response = await client.post(
                    f"{self.api_url}/command/",
                    headers=self.headers,
                    json=command_data,
                    timeout=15.0,
                )
                response.raise_for_status()

                # Some commands might not return JSON
                try:
                    return response.json()
                except Exception:
                    return {"result": response.text, "success": True}

        except httpx.HTTPStatusError as e:
            raise ObsidianAPIError(
                f"Command execution failed: {e.response.text}", e.response.status_code
            )
        except Exception as e:
            raise ObsidianAPIError(f"Connection error executing command: {str(e)}")

    # =================== Utility Methods ===================

    def normalize_path(self, path: str) -> str:
        """Normalize file path for consistent handling"""
        if not path:
            return ""

        # Remove leading/trailing slashes and whitespace
        path = path.strip(" /")

        # Ensure .md extension for notes
        if path and not path.endswith((".md", ".txt")):
            path += ".md"

        return path

    async def note_exists(self, path: str) -> bool:
        """Check if a note exists"""
        try:
            await self.read_note(path)
            return True
        except ObsidianAPIError as e:
            if e.status_code == 404:
                return False
            raise

    async def get_stats(self) -> Dict[str, Any]:
        """Get vault statistics"""
        try:
            structure = await self.get_vault_structure()
            vault_info = await self.get_vault_info()

            # Calculate additional stats
            total_size = sum(note.size for note in structure.notes)

            # Find largest and most recent notes
            largest_note = (
                max(structure.notes, key=lambda n: n.size) if structure.notes else None
            )
            most_recent = (
                max(structure.notes, key=lambda n: n.modified)
                if structure.notes
                else None
            )

            return {
                "vault_name": vault_info.get("name", "Unknown"),
                "vault_path": structure.root_path,
                "total_notes": structure.total_notes,
                "total_folders": structure.total_folders,
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "largest_note": {"path": largest_note.path, "size": largest_note.size}
                if largest_note
                else None,
                "most_recent_note": {
                    "path": most_recent.path,
                    "modified": most_recent.modified.isoformat(),
                }
                if most_recent
                else None,
                "api_url": self.api_url,
                "api_connected": await self.health_check(),
            }

        except Exception as e:
            if isinstance(e, ObsidianAPIError):
                raise
            raise ObsidianAPIError(f"Failed to get vault stats: {str(e)}")

    async def _discover_notes_in_folder(
        self, folder_path: str, notes_list: List[NoteMetadata]
    ):
        """
        Helper method to discover notes in a folder using available endpoints
        """
        try:
            # Try some common note patterns in the folder
            common_patterns = [
                "README.md",
                "index.md",
                "notes.md",
                "daily.md",
                "weekly.md",
                "template.md",
                "inbox.md",
                "todo.md",
            ]

            for pattern in common_patterns:
                test_path = f"{folder_path}/{pattern}"
                try:
                    # Try to read the note to see if it exists
                    content = await self.read_note(test_path)
                    # If successful, create metadata and add to list
                    note = NoteMetadata(
                        path=test_path,
                        name=pattern,
                        size=len(content),
                        modified=datetime.now(),  # We don't have real metadata
                        created=None,
                        tags=self.extract_tags(content) if content else [],
                    )
                    notes_list.append(note)
                except:
                    # File doesn't exist, continue
                    pass

        except Exception:
            # Ignore discovery errors
            pass
