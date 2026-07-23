"""
Obsidian filesystem-native client.

Reads and writes vault files directly on disk via a shared VaultCorpus - no
Obsidian REST API, no bearer token, no dependency on any Obsidian process
being alive. Public method names/signatures match the old REST client so
callers (src/tools/obsidian_tools.py, src/resources/obsidian_resources.py)
need no changes.
"""
import asyncio
import glob
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..scope import KNOWN_SCOPES
from ..vault_intelligence.corpus import ConcurrentModificationError, VaultCorpus

# Threshold matches scripts/obsidian-sync-watchdog.sh; kept in sync manually.
SYNC_STALE_THRESHOLD_SECONDS = 1800


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
    """Raised for note-not-found / already-exists / filesystem errors.

    Kept as the same exception shape the old REST client used (message +
    optional status_code) since callers pattern-match on status_code (e.g.
    404 -> "not found", 409 -> "already exists").
    """

    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


# Directory name components excluded from whole-vault scans (get_vault_structure,
# list_notes without a scope-prefixed folder). Anything dot-prefixed (.git,
# .trash, .obsidian, .mcp-write.lock's parent) plus stray non-vault dirs.
_EXCLUDED_DIR_NAMES = {"node_modules"}


def _is_excluded(rel_parts: Tuple[str, ...]) -> bool:
    return any(p.startswith(".") or p in _EXCLUDED_DIR_NAMES for p in rel_parts)


def _split_scope(path: str) -> Tuple[str, str]:
    """Every path reaching this client is scope-prefixed (obsidian_tools.py
    always resolves through src.scope.resolve_scoped_path first)."""
    p = (path or "").lstrip("/")
    if "/" not in p:
        raise ObsidianAPIError(f"Path must include a workspace scope prefix: {path!r}")
    scope, rel = p.split("/", 1)
    if scope not in KNOWN_SCOPES:
        raise ObsidianAPIError(
            f"Path must start with a workspace scope {KNOWN_SCOPES}: {path!r}"
        )
    return scope, rel


class ObsidianClient:
    """Filesystem-native client with full CRUD operations and vault management."""

    def __init__(self, corpus: Optional[VaultCorpus] = None):
        if corpus is not None:
            self.corpus = corpus
        else:
            vault_path = os.getenv("OBSIDIAN_VAULT_PATH", "")
            if not vault_path:
                raise ValueError("OBSIDIAN_VAULT_PATH environment variable is required")
            self.corpus = VaultCorpus(vault_path)
        self.vault_path = str(self.corpus.vault_path)

    # =================== Basic Vault Operations ===================

    async def get_vault_info(self) -> Dict[str, Any]:
        """Get vault information"""
        return {
            "name": self.corpus.vault_path.name or "Vault",
            "path": self.vault_path,
            "status": "connected" if os.path.isdir(self.vault_path) else "missing",
        }

    async def health_check(self) -> bool:
        """Vault path is present and readable on disk."""
        return os.path.isdir(self.vault_path)

    def _sync_health(self) -> Dict[str, Any]:
        """Sync freshness from obsidian-headless's per-vault sync.log mtime.

        Same signal the staleness watchdog (scripts/obsidian-sync-watchdog.sh)
        uses, read here so a stale vault is visible from inside an MCP
        conversation too, not only from the cron alert. Best-effort: if
        obsidian-headless isn't installed/configured (e.g. in tests, or on a
        machine that doesn't sync), reports "configured": False rather than
        erroring.
        """
        matches = glob.glob(
            os.path.expanduser("~/.config/obsidian-headless/sync/*/sync.log")
        )
        if not matches:
            return {"configured": False, "fresh": None, "age_seconds": None}

        log_path = max(matches, key=os.path.getmtime)
        try:
            age_seconds = time.time() - os.path.getmtime(log_path)
        except OSError:
            return {"configured": True, "fresh": None, "age_seconds": None}

        return {
            "configured": True,
            "fresh": age_seconds <= SYNC_STALE_THRESHOLD_SECONDS,
            "age_seconds": round(age_seconds, 1),
        }

    # =================== Note Reading Operations ===================

    async def read_note(self, path: str) -> str:
        """
        Read note content by path (must be scope-prefixed, e.g. "work/foo.md").
        Byte-for-byte parity with the old REST GET response.
        """
        if not path:
            raise ValueError("Note path cannot be empty")
        scope, rel = _split_scope(path)
        try:
            # Filesystem read released to a thread: a plain call here blocks
            # the whole (single-worker) event loop for the syscall's duration,
            # which is real wall-clock time on a network/cloud-synced vault.
            return await asyncio.to_thread(self.corpus.read_text, scope, rel)
        except FileNotFoundError:
            raise ObsidianAPIError(f"Note not found: {path}", 404)

    async def get_note_metadata(self, path: str) -> NoteMetadata:
        """Get note metadata including size, dates, etc."""
        scope, rel = _split_scope(path)
        full = self.corpus.full_path(scope, rel)
        try:
            stat = await asyncio.to_thread(full.stat)
        except OSError:
            raise ObsidianAPIError(f"Note metadata not found: {path}", 404)
        return NoteMetadata(
            path=path,
            name=full.name,
            size=stat.st_size,
            modified=datetime.fromtimestamp(stat.st_mtime),
            created=datetime.fromtimestamp(stat.st_ctime),
        )

    # =================== Note Writing Operations ===================

    async def create_note(
        self, path: str, content: str, create_folders: bool = True
    ) -> bool:
        """Create a new note. Raises 409 if it already exists."""
        if not path:
            raise ValueError("Note path cannot be empty")
        scope, rel = _split_scope(path)
        async with self.corpus.write_lock():
            exists = await asyncio.to_thread(self.corpus.note_exists, scope, rel)
            if exists:
                raise ObsidianAPIError(f"Note already exists: {path}", 409)
            try:
                await asyncio.to_thread(
                    self.corpus.write_note, scope, rel, content, create_folders=create_folders
                )
            except FileNotFoundError as e:
                raise ObsidianAPIError(f"Failed to write note {path}: {e}", 404)
        return True

    async def update_note(self, path: str, content: str) -> bool:
        """Overwrite an existing note's content. Raises 404 if it doesn't exist."""
        if not path:
            raise ValueError("Note path cannot be empty")
        scope, rel = _split_scope(path)
        async with self.corpus.write_lock():
            exists = await asyncio.to_thread(self.corpus.note_exists, scope, rel)
            if not exists:
                raise ObsidianAPIError(f"Note not found: {path}", 404)
            await asyncio.to_thread(
                self.corpus.write_note, scope, rel, content, create_folders=False
            )
        return True

    async def append_note(
        self, path: str, content: str, separator: str = "\n\n"
    ) -> bool:
        """Append content to an existing note (read-modify-write, lost-update guarded)."""
        if not path:
            raise ValueError("Note path cannot be empty")
        scope, rel = _split_scope(path)
        async with self.corpus.write_lock():
            exists = await asyncio.to_thread(self.corpus.note_exists, scope, rel)
            if not exists:
                raise ObsidianAPIError(f"Note not found: {path}", 404)
            try:
                await asyncio.to_thread(self.corpus.append_note, scope, rel, content, separator)
            except ConcurrentModificationError:
                raise ObsidianAPIError(
                    f"Note {path} changed concurrently while appending; please retry", 409
                )
        return True

    async def delete_note(self, path: str) -> bool:
        """Delete a note (moved to .trash/, not unlinked). Raises 404 if missing."""
        if not path:
            raise ValueError("Note path cannot be empty")
        scope, rel = _split_scope(path)
        async with self.corpus.write_lock():
            try:
                await asyncio.to_thread(self.corpus.delete_note, scope, rel)
            except FileNotFoundError:
                raise ObsidianAPIError(f"Note not found: {path}", 404)
        return True

    # =================== File and Folder Listing ===================

    def _walk_markdown(self, root: Path) -> List[Path]:
        """All .md files under root, skipping hidden dirs and node_modules."""
        if not root.is_dir():
            return []
        found: List[Path] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not _is_excluded((d,))]
            for name in filenames:
                if name.endswith(".md"):
                    found.append(Path(dirpath) / name)
        return found

    def _note_metadata_for(self, file_path: Path, include_tags: bool) -> Optional[NoteMetadata]:
        try:
            rel_path = str(file_path.relative_to(self.corpus.vault_path)).replace(os.sep, "/")
            stat = file_path.stat()
            tags = None
            if include_tags:
                try:
                    content = file_path.read_text(encoding="utf-8", errors="replace")[:2000]
                    tags = self._extract_tags(content)
                except OSError:
                    pass
            return NoteMetadata(
                path=rel_path,
                name=file_path.name,
                size=stat.st_size,
                modified=datetime.fromtimestamp(stat.st_mtime),
                created=datetime.fromtimestamp(stat.st_ctime),
                tags=tags,
            )
        except OSError:
            return None

    def _list_notes_sync(self, folder: Optional[str], include_tags: bool) -> List[NoteMetadata]:
        root = Path(self.vault_path) / folder if folder else Path(self.vault_path)
        notes = []
        for file_path in self._walk_markdown(root):
            note = self._note_metadata_for(file_path, include_tags)
            if note:
                notes.append(note)
        return notes

    async def list_notes(self, folder: Optional[str] = None, include_tags: bool = False) -> List[NoteMetadata]:
        """
        List notes with metadata under `folder` (scope-prefixed, e.g. "work" or
        "work/entities"). Falls back to a full vault scan if folder is omitted.

        Runs off the event loop: this walks the directory tree and stats (and,
        with include_tags, reads the head of) every matching file.
        """
        return await asyncio.to_thread(self._list_notes_sync, folder, include_tags)

    def _extract_tags(self, content: str) -> List[str]:
        """Extract tags from note content"""
        tags = set()

        if content.startswith("---"):
            try:
                end_idx = content.find("---", 3)
                if end_idx > 0:
                    frontmatter = content[3:end_idx]
                    for line in frontmatter.split("\n"):
                        if line.strip().startswith("tags:"):
                            tag_line = line.split(":", 1)[1].strip()
                            if tag_line.startswith("[") and tag_line.endswith("]"):
                                tag_list = tag_line[1:-1].split(",")
                                tags.update(
                                    tag.strip().strip("\"'") for tag in tag_list
                                )
                            else:
                                tags.update(tag.strip() for tag in tag_line.split(","))
            except Exception:
                pass

        inline_tags = re.findall(r"#([a-zA-Z0-9_/-]+)", content)
        tags.update(inline_tags)

        return list(tags)

    # =================== Vault Structure Operations ===================

    async def get_vault_structure(self, use_cache: bool = True, include_notes: bool = False) -> VaultStructure:
        """
        Get vault structure with folders and optionally notes.

        `use_cache` is accepted for signature parity but unused: a plain
        os.walk over an ~11MB vault is cheap enough that a separate TTL
        cache layer on top of it isn't worth the complexity (VaultCorpus
        already mtime-caches parsed note content). The walk itself still runs
        off the event loop (see `_get_vault_structure_sync`) since it's a
        real blocking syscall cost, not a CPU cost.
        """
        return await asyncio.to_thread(self._get_vault_structure_sync, include_notes)

    def _get_vault_structure_sync(self, include_notes: bool) -> VaultStructure:
        vault_root = Path(self.vault_path)
        all_md_files = self._walk_markdown(vault_root)

        folders: Dict[str, FolderInfo] = {}
        notes: List[NoteMetadata] = []
        note_paths = set()

        for file_path in all_md_files:
            rel_path = str(file_path.relative_to(vault_root)).replace(os.sep, "/")
            note_paths.add(rel_path)

            parent = file_path.parent
            while parent != vault_root and parent != parent.parent:
                folder_rel = str(parent.relative_to(vault_root)).replace(os.sep, "/")
                if folder_rel and folder_rel not in folders:
                    grandparent = parent.parent
                    parent_rel = (
                        str(grandparent.relative_to(vault_root)).replace(os.sep, "/")
                        if grandparent != vault_root
                        else None
                    )
                    folders[folder_rel] = FolderInfo(
                        path=folder_rel,
                        name=parent.name,
                        parent=parent_rel,
                    )
                parent = parent.parent

            if include_notes:
                note = self._note_metadata_for(file_path, include_tags=False)
                if note:
                    notes.append(note)

        for folder_path, folder_info in folders.items():
            folder_info.notes_count = sum(
                1
                for note_path in note_paths
                if note_path == folder_path or note_path.startswith(folder_path + "/")
            )
            folder_info.subfolders_count = sum(
                1
                for other_path in folders.keys()
                if other_path.startswith(folder_path + "/")
                and "/" not in other_path[len(folder_path) + 1 :]
            )

        total_notes = len(note_paths)

        structure = VaultStructure(
            root_path=self.vault_path,
            folders=list(folders.values()),
            notes=notes,
            total_notes=total_notes,
            total_folders=len(folders),
        )
        return structure

    async def get_folder_contents(self, folder_path: str) -> Dict[str, Any]:
        """Get contents of a specific folder"""
        folder_path = folder_path.strip("/")

        try:
            structure = await self.get_vault_structure(include_notes=True)

            folder_info = None
            for folder in structure.folders:
                if folder.path == folder_path:
                    folder_info = folder
                    break

            if not folder_info and folder_path != "":
                raise ObsidianAPIError(f"Folder not found: {folder_path}", 404)

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
        """Invalidate the shared corpus mtime cache."""
        self.corpus.clear_cache()

    # =================== Utility Methods ===================

    def normalize_path(self, path: str) -> str:
        """Normalize file path for consistent handling"""
        if not path:
            return ""
        path = path.strip(" /")
        if path and not path.endswith((".md", ".txt")):
            path += ".md"
        return path

    async def note_exists(self, path: str) -> bool:
        """Check if a note exists"""
        scope, rel = _split_scope(path)
        return await asyncio.to_thread(self.corpus.note_exists, scope, rel)

    async def get_stats(self) -> Dict[str, Any]:
        """Get vault statistics"""
        try:
            structure = await self.get_vault_structure(include_notes=True)
            vault_info = await self.get_vault_info()

            total_size = sum(note.size for note in structure.notes)

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
                "api_connected": await self.health_check(),
                "sync": self._sync_health(),
            }

        except Exception as e:
            if isinstance(e, ObsidianAPIError):
                raise
            raise ObsidianAPIError(f"Failed to get vault stats: {str(e)}")
