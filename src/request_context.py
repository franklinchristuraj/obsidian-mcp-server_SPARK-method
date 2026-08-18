"""Per-request MCP metadata (2026-07-28 _meta + legacy initialize caps).

Transport-level session state is gone; each request may carry protocol
version, client identity, and capabilities in params._meta (or the
legacy initialize handshake). Tools and tasks read this ContextVar —
never the singleton handler's mutable fields.
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

# Spec _meta keys (2026-07-28)
META_PROTOCOL_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CLIENT_INFO = "io.modelcontextprotocol/clientInfo"
META_CLIENT_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"

PROTOCOL_2026 = "2026-07-28"


@dataclass
class RequestMeta:
    """Request-scoped protocol metadata."""

    protocol_version: Optional[str] = None
    client_info: Dict[str, Any] = field(default_factory=dict)
    client_capabilities: Dict[str, Any] = field(default_factory=dict)
    is_modern: bool = False

    def supports_tasks(self) -> bool:
        """True when the client advertised the Tasks extension."""
        caps = self.client_capabilities or {}
        extensions = caps.get("extensions") or {}
        if not isinstance(extensions, dict):
            return False
        return "io.modelcontextprotocol/tasks" in extensions


request_meta: ContextVar[Optional[RequestMeta]] = ContextVar(
    "request_meta", default=None
)


def extract_meta_from_params(params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return the params._meta object if present and a dict."""
    if not isinstance(params, dict):
        return {}
    meta = params.get("_meta")
    return dict(meta) if isinstance(meta, dict) else {}


def build_request_meta(
    *,
    params: Optional[Dict[str, Any]],
    header_protocol_version: Optional[str],
) -> RequestMeta:
    """Build RequestMeta from HTTP header + params._meta / initialize fields."""
    meta = extract_meta_from_params(params)
    version = (
        header_protocol_version
        or meta.get(META_PROTOCOL_VERSION)
        or (params.get("protocolVersion") if isinstance(params, dict) else None)
    )
    if isinstance(version, str):
        version = version.strip() or None
    else:
        version = None

    client_info = meta.get(META_CLIENT_INFO)
    if not isinstance(client_info, dict):
        # Legacy initialize puts clientInfo at top level
        client_info = (
            params.get("clientInfo") if isinstance(params, dict) else None
        ) or {}
        if not isinstance(client_info, dict):
            client_info = {}

    client_caps = meta.get(META_CLIENT_CAPABILITIES)
    if not isinstance(client_caps, dict):
        client_caps = (
            params.get("capabilities") if isinstance(params, dict) else None
        ) or {}
        if not isinstance(client_caps, dict):
            client_caps = {}

    is_modern = version == PROTOCOL_2026 or header_protocol_version == PROTOCOL_2026
    return RequestMeta(
        protocol_version=version,
        client_info=dict(client_info),
        client_capabilities=dict(client_caps),
        is_modern=is_modern,
    )


def name_from_params(method: str, params: Optional[Dict[str, Any]]) -> Optional[str]:
    """Extract the tool/prompt/resource name for Mcp-Name validation."""
    if not isinstance(params, dict):
        return None
    if method == "tools/call":
        name = params.get("name")
        return str(name) if name is not None else None
    if method == "prompts/get":
        name = params.get("name")
        return str(name) if name is not None else None
    if method == "resources/read":
        uri = params.get("uri")
        return str(uri) if uri is not None else None
    return None
