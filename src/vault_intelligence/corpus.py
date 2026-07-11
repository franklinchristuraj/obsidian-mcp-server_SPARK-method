"""Mtime-keyed in-process corpus cache for vault intelligence tools."""
from __future__ import annotations

import asyncio
import contextlib
import fcntl
import os
import shutil
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .entity_index import build_name_index
from .parser import ParsedNote, normalize_path_key, parse_note


class ConcurrentModificationError(Exception):
    """A read-modify-write lost the race to a concurrent writer (e.g. sync pull)."""


class VaultCorpus:
    """Live-read corpus with per-file mtime cache."""

    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path)
        self._cache: Dict[str, Tuple[float, ParsedNote]] = {}
        self._alock = asyncio.Lock()
        self._lock_owner: Optional[asyncio.Task] = None
        self._lock_depth = 0

    def clear_cache(self) -> None:
        self._cache.clear()

    def _cache_key(self, scope: str, workspace_rel: str) -> str:
        return f"{scope}/{workspace_rel}"

    def get_note(
        self,
        scope: str,
        workspace_rel: str,
        *,
        include_sections: bool = True,
    ) -> Optional[ParsedNote]:
        """Load one note by workspace-relative path."""
        rel = workspace_rel.replace("\\", "/").lstrip("/")
        full = self.vault_path / scope / rel
        if not full.is_file():
            if not rel.endswith(".md"):
                full = self.vault_path / scope / f"{rel}.md"
            if not full.is_file():
                return None
            rel = str(full.relative_to(self.vault_path / scope)).replace("\\", "/")

        try:
            mtime = full.stat().st_mtime
        except OSError:
            return None

        key = self._cache_key(scope, rel)
        if not include_sections:
            key = f"{key}:light"
        cached = self._cache.get(key)
        if cached and cached[0] == mtime:
            return cached[1]

        note = parse_note(
            full, scope, rel, include_sections=include_sections, mtime=mtime
        )
        self._cache[key] = (mtime, note)
        return note

    def load_scope(
        self,
        scopes: List[str],
        folder: Optional[str] = None,
        *,
        include_sections: bool = True,
    ) -> List[ParsedNote]:
        """Load all notes under scope(s), optionally limited to folder."""
        notes: List[ParsedNote] = []
        for scope in scopes:
            root = self.vault_path / scope
            if not root.is_dir():
                continue
            if folder:
                folder = folder.strip().strip("/")
                search_root = root / folder
            else:
                search_root = root
            if not search_root.is_dir():
                continue
            for path in search_root.rglob("*.md"):
                if not path.is_file():
                    continue
                rel = str(path.relative_to(root)).replace("\\", "/")
                note = self.get_note(scope, rel, include_sections=include_sections)
                if note:
                    notes.append(note)
        return notes

    def index_by_path(self, notes: List[ParsedNote]) -> Dict[str, ParsedNote]:
        """Map normalized path keys to ParsedNote."""
        idx: Dict[str, ParsedNote] = {}
        for note in notes:
            idx[normalize_path_key(note.path)] = note
        return idx

    def index_by_name(self, notes: List[ParsedNote]) -> Dict[str, ParsedNote]:
        """Map bare filename-stems and aliases to ParsedNote for bare-wikilink resolution.

        Event entities use bare links like ``[[claroty]]`` (Obsidian alias
        resolution) instead of full-path links. This index lets the intelligence
        tools resolve those to canonical ``entities/...`` paths. Keys that collide
        across two different notes are dropped so a bare link never resolves to an
        ambiguous target. Delegates to entity_index.build_name_index, the single
        source of truth for this resolution rule; see there for the full
        ambiguity-drop rationale and for the sibling EntityIndex used at write time.
        """
        idx, _ambiguous = build_name_index(notes)
        return idx

    def vault_file_exists(self, scope: str, workspace_rel: str) -> bool:
        rel = workspace_rel.replace("\\", "/").lstrip("/")
        full = self.vault_path / scope / rel
        if full.is_file():
            return True
        if not rel.endswith(".md"):
            return (self.vault_path / scope / f"{rel}.md").is_file()
        return False

    def resolve_vault_path(self, scope: str, link: str) -> Optional[str]:
        """Resolve wikilink to workspace-relative path if file exists."""
        link = link.replace("\\", "/").lstrip("/")
        candidates = [link]
        if not link.endswith(".md"):
            candidates.append(f"{link}.md")
        for c in candidates:
            if self.vault_file_exists(scope, c):
                return c if c.endswith(".md") else c
        return None

    # =================== CRUD (filesystem-native) ===================
    #
    # Literal path resolution on purpose: no fuzzy ".md" guessing here, unlike
    # get_note(). These back ObsidianClient's CRUD tools, which need exact
    # parity with the old REST client's literal-path semantics.

    def _resolve_full_path(self, scope: str, workspace_rel: str) -> Tuple[Path, str]:
        rel = workspace_rel.replace("\\", "/").lstrip("/")
        return self.vault_path / scope / rel, rel

    def full_path(self, scope: str, workspace_rel: str) -> Path:
        full, _ = self._resolve_full_path(scope, workspace_rel)
        return full

    def note_exists(self, scope: str, workspace_rel: str) -> bool:
        full, _ = self._resolve_full_path(scope, workspace_rel)
        return full.is_file()

    def read_text(self, scope: str, workspace_rel: str) -> str:
        full, rel = self._resolve_full_path(scope, workspace_rel)
        try:
            return full.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise FileNotFoundError(rel) from None

    def stat_mtime(self, scope: str, workspace_rel: str) -> Optional[float]:
        full, _ = self._resolve_full_path(scope, workspace_rel)
        try:
            return full.stat().st_mtime
        except OSError:
            return None

    def write_note(
        self,
        scope: str,
        workspace_rel: str,
        content: str,
        *,
        create_folders: bool = True,
        expected_mtime: Optional[float] = None,
    ) -> None:
        """Atomic write: temp file in the same directory + os.replace().

        If ``expected_mtime`` is given (read-modify-write callers, e.g.
        append_note), the current on-disk mtime is re-checked immediately
        before the replace; a mismatch means a concurrent writer (sync pull,
        another call) landed in between, and raises ConcurrentModificationError
        instead of silently clobbering it.
        """
        full, rel = self._resolve_full_path(scope, workspace_rel)
        if create_folders:
            full.parent.mkdir(parents=True, exist_ok=True)
        elif not full.parent.is_dir():
            raise FileNotFoundError(f"Parent folder does not exist: {full.parent}")

        if expected_mtime is not None:
            try:
                current_mtime: Optional[float] = full.stat().st_mtime
            except OSError:
                current_mtime = None
            if current_mtime != expected_mtime:
                raise ConcurrentModificationError(rel)

        tmp = full.parent / f".{full.name}.tmp-{os.getpid()}-{time.time_ns()}"
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, full)
        self._invalidate(scope, rel)

    def append_note(self, scope: str, workspace_rel: str, content: str, separator: str = "\n\n") -> None:
        """Read-modify-write append, retried once on a lost-update race."""
        _, rel = self._resolve_full_path(scope, workspace_rel)
        for attempt in range(2):
            existing = self.read_text(scope, rel)
            mtime = self.stat_mtime(scope, rel)
            new_content = existing + separator + content
            try:
                self.write_note(scope, rel, new_content, create_folders=False, expected_mtime=mtime)
                return
            except ConcurrentModificationError:
                if attempt == 1:
                    raise
                continue

    def delete_note(self, scope: str, workspace_rel: str) -> None:
        """Move to .trash/ (vault root, outside every scope dir) instead of unlinking."""
        full, rel = self._resolve_full_path(scope, workspace_rel)
        if not full.is_file():
            raise FileNotFoundError(rel)
        trash_dir = self.vault_path / ".trash" / scope / str(Path(rel).parent)
        trash_dir.mkdir(parents=True, exist_ok=True)
        dest = trash_dir / full.name
        if dest.exists():
            ts = time.strftime("%Y%m%d-%H%M%S")
            dest = trash_dir / f"{full.stem}-{ts}{full.suffix}"
        shutil.move(str(full), str(dest))
        self._invalidate(scope, rel)

    def _invalidate(self, scope: str, rel: str) -> None:
        key = self._cache_key(scope, rel)
        self._cache.pop(key, None)
        self._cache.pop(f"{key}:light", None)

    def write_lock(self):
        """Coarse, reentrant-per-task write lock.

        asyncio.Lock serializes concurrent MCP write-tool calls within this
        process; the fcntl.flock on `.mcp-write.lock` (vault root) extends
        that to any other process touching the same vault. Reentrant so a
        multi-step flow (e.g. create_event calling create_note, then reading
        and updating backref notes) can hold it across its whole sequence
        without a nested acquire deadlocking.
        """
        return _WriteLock(self)


class _WriteLock:
    def __init__(self, corpus: VaultCorpus):
        self._corpus = corpus
        self._fd: Optional[int] = None

    async def __aenter__(self):
        c = self._corpus
        task = asyncio.current_task()
        if c._lock_owner is task:
            c._lock_depth += 1
            return self

        await c._alock.acquire()
        c._lock_owner = task
        c._lock_depth = 1
        lock_path = c.vault_path / ".mcp-write.lock"
        self._fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
        await asyncio.to_thread(fcntl.flock, self._fd, fcntl.LOCK_EX)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        c = self._corpus
        c._lock_depth -= 1
        if c._lock_depth > 0:
            return False
        if self._fd is not None:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None
        c._lock_owner = None
        c._alock.release()
        return False
