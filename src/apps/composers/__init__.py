"""Shared helpers for MCP App composers."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from src.tools.obsidian_tools import obsidian_tools
from src.scope import KNOWN_SCOPES


def payload_from_tool_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract structured payload from an Obsidian tool result."""
    if isinstance(result.get("metadata"), dict):
        return result["metadata"]
    content = result.get("content") or []
    if content and isinstance(content[0], dict) and "text" in content[0]:
        return json.loads(content[0]["text"])
    raise ValueError("Tool result missing structured payload")


async def call_vault(method_name: str, **kwargs: Any) -> Dict[str, Any]:
    """Call an ObsidianTools method and return its structured payload."""
    method = getattr(obsidian_tools, method_name)
    result = await method(**kwargs)
    return payload_from_tool_result(result)


def require_scope(scope: Optional[str], *, allowed: Optional[tuple] = None) -> str:
    if not scope:
        raise ValueError("scope is required and must be explicit")
    scopes = allowed or KNOWN_SCOPES
    if scope not in scopes:
        raise ValueError(f"scope must be one of {scopes}, got {scope!r}")
    return scope
