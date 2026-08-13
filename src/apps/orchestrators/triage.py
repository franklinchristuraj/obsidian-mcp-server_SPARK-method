"""Triage write paths: promote_capture + archive_capture."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from src.apps.composers import require_scope
from src.scope import get_effective_workspace_context, resolve_write_scope
from src.tools.obsidian_tools import obsidian_tools

_TARGET_FOLDERS = {
    "01_seeds": "seed",
    "04_resources": "resource",
    "05_knowledge": "knowledge",
}


def _parse_frontmatter(text: str) -> tuple[Dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    try:
        fm = yaml.safe_load(parts[1]) or {}
    except Exception:
        fm = {}
    return fm, parts[2]


def _dump_note(fm: Dict[str, Any], body: str) -> str:
    dumped = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{dumped}\n---\n{body}"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:64] or "note"


async def promote_capture(
    path: str,
    scope: str,
    target_folder: str,
    target_type: str,
    title: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    scope = require_scope(scope)
    ctx = get_effective_workspace_context()
    try:
        scope = resolve_write_scope(scope, tuple(ctx.effective_write_scopes))
    except (PermissionError, ValueError) as e:
        if isinstance(e, PermissionError):
            raise ValueError("Access denied") from e
        raise
    if target_folder not in _TARGET_FOLDERS:
        raise ValueError(
            f"target_folder must be one of {sorted(_TARGET_FOLDERS)}, got {target_folder!r}"
        )
    expected_type = _TARGET_FOLDERS[target_folder]
    if target_type != expected_type:
        # Allow explicit override only if it matches folder convention loosely
        if target_type not in ("seed", "resource", "knowledge"):
            raise ValueError(f"invalid target_type: {target_type!r}")

    client = obsidian_tools.client
    if client is None:
        raise ValueError("Obsidian client not initialized")

    rel = path.lstrip("/")
    if not rel.startswith("01_seeds/"):
        raise ValueError("promote_capture only accepts root 01_seeds/ paths")

    src = Path(client.vault_path) / rel
    if not src.is_file():
        raise ValueError(f"Capture not found: {rel}")

    text = src.read_text(encoding="utf-8")
    fm, body = _parse_frontmatter(text)
    fm["type"] = target_type
    if "status" in fm:
        fm["status"] = "active"
    if title:
        fm["title"] = title
    if tags is not None:
        fm["tags"] = tags
    fm.pop("target_scope", None)

    filename = src.name
    if title:
        # Keep date prefix if present
        prefix = ""
        m = re.match(r"^(\d{4}-\d{2}-\d{2}(?:_\d{4})?)_", filename)
        if m:
            prefix = m.group(1) + "_"
        filename = f"{prefix}{_slug(title)}.md"

    dest_rel_scoped = f"{target_folder}/{filename}"
    dest = Path(client.vault_path) / scope / dest_rel_scoped
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        stem = dest.stem
        dest = dest.with_name(f"{stem}-promoted{dest.suffix}")
        dest_rel_scoped = f"{target_folder}/{dest.name}"

    new_text = _dump_note(fm, body)
    dest.write_text(new_text, encoding="utf-8")
    src.unlink()

    return {
        "ok": True,
        "old_path": rel,
        "new_path": f"{scope}/{dest_rel_scoped}",
        "scope": scope,
        "target_type": target_type,
        "target_folder": target_folder,
    }


async def archive_capture(path: str) -> Dict[str, Any]:
    """Move root capture to vault-root 99_archive/ (never hard delete)."""
    client = obsidian_tools.client
    if client is None:
        raise ValueError("Obsidian client not initialized")

    rel = path.lstrip("/")
    if not rel.startswith("01_seeds/"):
        raise ValueError("archive_capture only accepts root 01_seeds/ paths")

    src = Path(client.vault_path) / rel
    if not src.is_file():
        raise ValueError(f"Capture not found: {rel}")

    archive_dir = Path(client.vault_path) / "99_archive" / "01_seeds"
    archive_dir.mkdir(parents=True, exist_ok=True)
    dest = archive_dir / src.name
    if dest.exists():
        dest = archive_dir / f"{src.stem}-archived{src.suffix}"
    src.rename(dest)

    return {
        "ok": True,
        "old_path": rel,
        "new_path": str(dest.relative_to(client.vault_path)).replace("\\", "/"),
    }
