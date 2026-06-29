"""Mtime-keyed in-process corpus cache for vault intelligence tools."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .parser import ParsedNote, normalize_path_key, parse_note


class VaultCorpus:
    """Live-read corpus with per-file mtime cache."""

    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path)
        self._cache: Dict[str, Tuple[float, ParsedNote]] = {}

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
        ambiguous target.
        """
        idx: Dict[str, ParsedNote] = {}
        ambiguous: set = set()

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
