"""Multi Round-Trip Requests (MRTR) for destructive write confirmations.

When a gated tool is called without a prior confirmation, return
InputRequiredResult (resultType=input_required). The client retries with
inputResponses + echoed requestState; we then execute the write.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict, Optional, Tuple

from .request_context import RequestMeta
from .scope import workspace_ctx

# Tools that always require confirmation
ALWAYS_GATED = frozenset(
    {"delete_note", "rename_note", "archive_capture"}
)

CONFIRM_REQUEST_ID = "confirm"

# HMAC secret for requestState (set MRTR_STATE_SECRET in prod)
_STATE_SECRET = os.getenv(
    "MRTR_STATE_SECRET", "dev-mrtr-state-secret-change-me"
).encode("utf-8")
_STATE_TTL_SECONDS = int(os.getenv("MRTR_STATE_TTL_SECONDS", "300"))


def _arg_digest(arguments: Dict[str, Any]) -> str:
    canonical = json.dumps(arguments or {}, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def mint_request_state(
    *,
    identity: str,
    tool_name: str,
    arguments: Dict[str, Any],
) -> str:
    """Opaque HMAC-signed state binding identity, tool, args, expiry."""
    payload = {
        "identity": identity,
        "tool": tool_name,
        "args": _arg_digest(arguments),
        "exp": int(time.time()) + _STATE_TTL_SECONDS,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    sig = hmac.new(_STATE_SECRET, raw, hashlib.sha256).digest()
    return (
        base64.urlsafe_b64encode(raw).decode("ascii")
        + "."
        + base64.urlsafe_b64encode(sig).decode("ascii")
    )


def validate_request_state(
    state: str,
    *,
    identity: str,
    tool_name: str,
    arguments: Dict[str, Any],
) -> Tuple[bool, str]:
    """Return (ok, error_message)."""
    try:
        raw_b64, sig_b64 = state.split(".", 1)
        raw = base64.urlsafe_b64decode(raw_b64.encode("ascii"))
        sig = base64.urlsafe_b64decode(sig_b64.encode("ascii"))
    except Exception:
        return False, "Malformed requestState"
    expected = hmac.new(_STATE_SECRET, raw, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected):
        return False, "Invalid requestState signature"
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return False, "Invalid requestState payload"
    if payload.get("identity") != identity:
        return False, "requestState identity mismatch"
    if payload.get("tool") != tool_name:
        return False, "requestState tool mismatch"
    if payload.get("args") != _arg_digest(arguments):
        return False, "requestState arguments mismatch"
    if int(payload.get("exp", 0)) < int(time.time()):
        return False, "requestState expired"
    return True, ""


def needs_confirmation(tool_name: str, arguments: Dict[str, Any]) -> bool:
    if tool_name in ALWAYS_GATED:
        return True
    if tool_name == "lint_vault" and bool(arguments.get("fix")):
        return True
    return False


def supports_mrtr(meta: Optional[RequestMeta]) -> bool:
    """True when the client can fulfill elicitation / MRTR."""
    if meta is None:
        return False
    # Modern 2026-07-28 clients are expected to speak MRTR
    if meta.is_modern:
        return True
    caps = meta.client_capabilities or {}
    if "elicitation" in caps:
        return True
    # Some clients nest under experimental / extensions
    extensions = caps.get("extensions") or {}
    if isinstance(extensions, dict) and (
        "elicitation" in extensions
        or "io.modelcontextprotocol/elicitation" in extensions
    ):
        return True
    return False


def _summary(tool_name: str, arguments: Dict[str, Any]) -> str:
    args = arguments or {}
    if tool_name == "delete_note":
        return (
            f"Delete note {args.get('path')!r} "
            f"(scope={args.get('scope')!r}). This moves it to trash."
        )
    if tool_name == "rename_note":
        return (
            f"Rename {args.get('path')!r} → {args.get('new_path')!r} "
            f"(update_backlinks={args.get('update_backlinks', True)})."
        )
    if tool_name == "lint_vault":
        return (
            f"Run lint_vault with fix=true on scope={args.get('scope')!r}. "
            "This will write corrections into the vault."
        )
    if tool_name == "archive_capture":
        return (
            f"Archive capture {args.get('path')!r} to 99_archive/ "
            "(not a hard delete)."
        )
    return f"Confirm destructive action: {tool_name}"


def build_input_required(
    *,
    tool_name: str,
    arguments: Dict[str, Any],
    identity: str,
) -> Dict[str, Any]:
    """MCP InputRequiredResult for tools/call."""
    state = mint_request_state(
        identity=identity, tool_name=tool_name, arguments=arguments
    )
    message = _summary(tool_name, arguments)
    elicitation = {
        "method": "elicitation/create",
        "params": {
            "message": message,
            "requestedSchema": {
                "type": "object",
                "properties": {
                    "confirm": {
                        "type": "boolean",
                        "description": "Set true to proceed with this write.",
                    }
                },
                "required": ["confirm"],
            },
        },
    }
    payload = {
        "resultType": "input_required",
        "inputRequests": {CONFIRM_REQUEST_ID: elicitation},
        "requestState": state,
        "message": message,
    }
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, indent=2),
            }
        ],
        "structuredContent": payload,
        "metadata": payload,
        # Spec-shaped fields also at top level for clients that look there
        "resultType": "input_required",
        "inputRequests": payload["inputRequests"],
        "requestState": state,
    }


def confirmation_refused_error(tool_name: str) -> Dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"Confirmation required for '{tool_name}' but was not "
                    "granted (confirm=false or missing)."
                ),
            }
        ],
        "isError": True,
    }


def mrtr_unsupported_error(tool_name: str) -> Dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"Destructive tool '{tool_name}' requires MRTR/elicitation "
                    "confirmation. This client did not advertise elicitation "
                    "support, so the write was not executed. Retry from a "
                    "host that supports Multi Round-Trip Requests."
                ),
            }
        ],
        "isError": True,
    }


def extract_confirmation(
    params: Dict[str, Any],
) -> Tuple[Optional[str], Optional[bool]]:
    """Pull requestState + confirm from tools/call params."""
    state = params.get("requestState")
    if state is None and isinstance(params.get("_meta"), dict):
        state = params["_meta"].get("requestState")
    responses = params.get("inputResponses") or {}
    if not isinstance(responses, dict):
        responses = {}
    confirm: Optional[bool] = None
    entry = responses.get(CONFIRM_REQUEST_ID)
    if isinstance(entry, dict):
        # elicitation response shape: { "content": { "confirm": true } }
        # or flat { "confirm": true }
        content = entry.get("content") if "content" in entry else entry
        if isinstance(content, dict) and "confirm" in content:
            confirm = bool(content.get("confirm"))
        elif "confirm" in entry:
            confirm = bool(entry.get("confirm"))
    return (str(state) if state else None), confirm


def gate_destructive_call(
    tool_name: str,
    arguments: Dict[str, Any],
    params: Dict[str, Any],
    meta: Optional[RequestMeta],
) -> Optional[Dict[str, Any]]:
    """
    If this call needs confirmation and is not yet confirmed, return a
    tools/call result (input_required or isError). Return None to proceed.
    """
    if not needs_confirmation(tool_name, arguments or {}):
        return None

    ctx = workspace_ctx.get()
    if ctx is None:
        return {
            "content": [{"type": "text", "text": "Not authenticated"}],
            "isError": True,
        }

    state, confirm = extract_confirmation(params)
    if state is not None:
        ok, err = validate_request_state(
            state,
            identity=ctx.identity,
            tool_name=tool_name,
            arguments=arguments or {},
        )
        if not ok:
            return {
                "content": [{"type": "text", "text": f"MRTR rejected: {err}"}],
                "isError": True,
            }
        if confirm is True:
            return None  # proceed
        return confirmation_refused_error(tool_name)

    if not supports_mrtr(meta):
        return mrtr_unsupported_error(tool_name)

    return build_input_required(
        tool_name=tool_name,
        arguments=arguments or {},
        identity=ctx.identity,
    )
