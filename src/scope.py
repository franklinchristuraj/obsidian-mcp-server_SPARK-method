"""
Workspace scope resolution for MCP tools (connection-level enforcement).
"""
from __future__ import annotations

import os
from contextvars import ContextVar
from dataclasses import dataclass
from typing import List, Optional, Tuple


KNOWN_SCOPES: Tuple[str, ...] = ("personal", "passion", "work")


@dataclass(frozen=True)
class WorkspaceContext:
    """Per-request workspace access (set from API key / OAuth mapping)."""

    identity: str
    allowed_scopes: Tuple[str, ...]
    role: str
    display_name: str = ""


workspace_ctx: ContextVar[Optional[WorkspaceContext]] = ContextVar(
    "workspace_ctx", default=None
)


def parse_default_workspace_scopes() -> Tuple[str, ...]:
    """Scopes when a key/client has no explicit entry in workspace_keys.json."""
    raw = os.getenv("MCP_DEFAULT_WORKSPACE_SCOPES", "personal,passion,work")
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    validated = [p for p in parts if p in KNOWN_SCOPES]
    if not validated:
        return tuple(KNOWN_SCOPES)
    return tuple(dict.fromkeys(validated))  # preserve order, dedupe


def get_effective_workspace_context() -> WorkspaceContext:
    """Context from HTTP request, or env defaults for local/tests without middleware."""
    ctx = workspace_ctx.get()
    if ctx is not None:
        return ctx
    return WorkspaceContext(
        identity="local-default",
        allowed_scopes=parse_default_workspace_scopes(),
        role="admin",
        display_name="Default",
    )


def _validate_scope(scope: str, allowed_scopes: Tuple[str, ...]) -> None:
    if scope not in KNOWN_SCOPES:
        raise ValueError(f"Invalid scope: {scope}")
    if scope not in allowed_scopes:
        raise PermissionError("Access denied")


def forbid_scope_prefix_in_agent_path(user_path: str) -> None:
    """Agents must pass workspace via `scope`, not as the first path segment."""
    user_path = user_path.lstrip("/")
    if not user_path:
        return
    first = user_path.split("/")[0]
    if first in KNOWN_SCOPES:
        raise ValueError(
            "Do not include the workspace name in the path; use the scope parameter instead."
        )


def resolve_scoped_path(
    user_path: str, scope: str, allowed_scopes: Tuple[str, ...]
) -> str:
    """
    Returns vault-relative path: {scope}/{user_path}.
    Raises PermissionError or ValueError on invalid input.
    """
    _validate_scope(scope, allowed_scopes)
    user_path = user_path.lstrip("/")
    if not user_path:
        raise ValueError("Path cannot be empty")
    if user_path.startswith("/") or ".." in user_path.split("/"):
        raise ValueError("Invalid path")
    forbid_scope_prefix_in_agent_path(user_path)
    return f"{scope}/{user_path}"


def strip_scope_prefix(
    full_path: str, allowed_scopes: Tuple[str, ...]
) -> Tuple[str, Optional[str]]:
    """
    If full_path starts with an allowed scope prefix, return (relative_path, scope).
    Otherwise returns (full_path, None).
    """
    full_path = full_path.lstrip("/")
    for scope in allowed_scopes:
        if full_path == scope:
            return "", scope
        prefix = scope + "/"
        if full_path.startswith(prefix):
            return full_path[len(prefix) :], scope
    return full_path, None


def active_scopes_for_read(
    scope_param: Optional[str], allowed_scopes: Tuple[str, ...]
) -> List[str]:
    """Scopes to include for read/search/list operations."""
    if scope_param is None or scope_param == "":
        return list(allowed_scopes)
    if scope_param not in KNOWN_SCOPES:
        raise ValueError(f"Invalid scope: {scope_param}")
    if scope_param not in allowed_scopes:
        raise PermissionError("Access denied")
    return [scope_param]


def resolve_write_scope(
    scope_param: Optional[str], allowed_scopes: Tuple[str, ...]
) -> str:
    """
    Single allowed scope -> auto-selected. Multiple -> scope_param required.
    """
    if len(allowed_scopes) == 1:
        only = allowed_scopes[0]
        if scope_param is None or scope_param == "":
            return only
        _validate_scope(scope_param, allowed_scopes)
        return scope_param
    if scope_param is None or scope_param == "":
        raise ValueError(
            "This API key has access to multiple workspaces; you must pass scope."
        )
    _validate_scope(scope_param, allowed_scopes)
    return scope_param


def scoped_list_folder(folder: str, scope: str) -> str:
    """Prefix optional agent folder with workspace for Obsidian list_notes."""
    folder = folder.strip().strip("/") if folder else ""
    if not folder:
        return scope
    forbid_scope_prefix_in_agent_path(folder)
    return f"{scope}/{folder}"
