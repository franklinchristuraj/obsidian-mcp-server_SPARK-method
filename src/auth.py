"""
Authentication Middleware
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional, Tuple

from fastapi import Header, HTTPException, Request, status

from src.scope import (
    WorkspaceContext,
    parse_default_workspace_scopes,
    KNOWN_SCOPES,
)


_workspace_config_cache: Optional[Dict[str, Any]] = None


def _load_workspace_config() -> Dict[str, Any]:
    global _workspace_config_cache
    if _workspace_config_cache is not None:
        return _workspace_config_cache
    path = os.getenv("WORKSPACE_KEYS_PATH", "workspace_keys.json")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            _workspace_config_cache = json.load(f)
    else:
        _workspace_config_cache = {"keys": {}, "oauth_clients": {}}
    return _workspace_config_cache


def clear_workspace_config_cache() -> None:
    """For tests."""
    global _workspace_config_cache
    _workspace_config_cache = None


def _normalize_scopes(raw: Any) -> Tuple[str, ...]:
    if not isinstance(raw, list):
        return parse_default_workspace_scopes()
    out = [str(s) for s in raw if str(s) in KNOWN_SCOPES]
    if not out:
        return parse_default_workspace_scopes()
    return tuple(dict.fromkeys(out))


def _entry_to_context(identity: str, entry: Dict[str, Any]) -> WorkspaceContext:
    return WorkspaceContext(
        identity=identity,
        allowed_scopes=_normalize_scopes(entry.get("scopes")),
        role=str(entry.get("role", "user")),
        display_name=str(entry.get("name", "")),
    )


async def verify_api_key(
    request: Request,
    authorization: str = Header(None),
) -> WorkspaceContext:
    """
    Verify Bearer token from Authorization header and attach workspace scopes.

    Accepts:
    1. Keys listed in workspace_keys.json (Bearer value matches key string)
    2. MCP_API_KEY from env (uses keys[secret] if present, else MCP_DEFAULT_WORKSPACE_SCOPES)
    3. OAuth access tokens in the SQLite token store (uses oauth_clients[client_id] or default scopes)
    """
    require_auth = os.getenv("MCP_REQUIRE_AUTH", "true").lower() == "true"
    defaults = parse_default_workspace_scopes()

    if not require_auth:
        return WorkspaceContext(
            identity="proxy-authenticated",
            allowed_scopes=defaults,
            role="admin",
            display_name="Auth disabled",
        )

    token = None
    if authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]

    if not token:
        token = request.query_params.get("api_key") or request.headers.get("X-API-Key")

    if not token:
        print(
            f"🔐 AUTH FAIL [no token] UA={request.headers.get('user-agent', '?')} "
            f"headers={dict(request.headers)}"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header or api_key parameter",
        )

    print(f"🔐 AUTH token={token[:20]}... UA={request.headers.get('user-agent', '?')}")
    config = _load_workspace_config()
    keys = config.get("keys") or {}
    oauth_clients = config.get("oauth_clients") or {}

    if isinstance(keys, dict) and token in keys and isinstance(keys[token], dict):
        return _entry_to_context(f"key:{token[:12]}…", keys[token])

    expected_key = os.getenv("MCP_API_KEY")
    if expected_key and token == expected_key:
        if expected_key in keys and isinstance(keys[expected_key], dict):
            return _entry_to_context("static-api-key", keys[expected_key])
        return WorkspaceContext(
            identity="static-api-key",
            allowed_scopes=defaults,
            role="admin",
            display_name="Static MCP_API_KEY",
        )

    try:
        from main import token_store

        token_data = await token_store.get_access_token(token)
        if token_data is not None:
            client_id = token_data["client_id"]
            if client_id in oauth_clients and isinstance(oauth_clients[client_id], dict):
                return _entry_to_context(client_id, oauth_clients[client_id])
            return WorkspaceContext(
                identity=client_id,
                allowed_scopes=defaults,
                role="user",
                display_name="OAuth client (default scopes)",
            )
    except Exception:
        pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token invalid or expired",
    )
