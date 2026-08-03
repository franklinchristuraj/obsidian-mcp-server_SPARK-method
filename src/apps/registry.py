"""MCP Apps registry: UI resources + tool definitions + dispatch."""
from __future__ import annotations

import json
from typing import Any, Awaitable, Callable, Dict, List, Optional

from src.types import MCPResource, MCPTool

from .paths import (
    DEFAULT_UI_CSP,
    UI_MIME_TYPE,
    dist_html_path,
    split_ui_uri,
    ui_uri,
)

Handler = Callable[..., Awaitable[Dict[str, Any]]]

# App name → human label for resources/list
_UI_APPS: Dict[str, str] = {
    "smoke": "MCP Apps smoke test",
    "prep-card": "Prep Card",
    "lint-queue": "Lint Queue",
    "snapshot-entry": "Snapshot Entry",
    "debrief-form": "Debrief Form",
    "triage-board": "Triage Board",
}


def _ui_meta(resource_uri: str, visibility: Optional[List[str]] = None) -> Dict[str, Any]:
    meta: Dict[str, Any] = {"ui": {"resourceUri": resource_uri}}
    if visibility is not None:
        meta["ui"]["visibility"] = visibility
    return meta


def _resource_meta() -> Dict[str, Any]:
    return {"ui": {"csp": dict(DEFAULT_UI_CSP)}}


def list_ui_app_resources() -> List[MCPResource]:
    """Return MCPResource entries for every registered UI bundle that exists on disk."""
    resources: List[MCPResource] = []
    for app_name, label in _UI_APPS.items():
        path = dist_html_path(app_name)
        if not path.is_file():
            continue
        resources.append(
            MCPResource(
                uri=ui_uri(app_name),
                name=label,
                description=f"Ziksaka MCP App · {label}",
                mimeType=UI_MIME_TYPE,
                meta=_resource_meta(),
            )
        )
    return resources


def read_ui_app_resource(uri: str) -> Dict[str, Any]:
    """
    Read a ui://ziksaka/{app}[@version] HTML bundle.

    The version suffix is a cache-busting content hash, so it is ignored when
    resolving the bundle on disk; any version of a known app reads the current
    file.

    Returns dict with keys: uri, mimeType, text, metadata (_meta.ui.csp).
    Raises ValueError if unknown or missing on disk.
    """
    app_name, _version = split_ui_uri(uri)
    if app_name not in _UI_APPS:
        raise ValueError(f"No MCP App UI registered for {uri}")
    path = dist_html_path(app_name)
    if not path.is_file():
        raise ValueError(
            f"UI bundle missing for {uri} (expected {path}). "
            "Build apps with `npm run build` in apps/."
        )
    text = path.read_text(encoding="utf-8")
    return {
        "uri": uri,
        "mimeType": UI_MIME_TYPE,
        "text": text,
        "metadata": _resource_meta(),
    }


def _tool(
    name: str,
    description: str,
    properties: Dict[str, Any],
    required: List[str],
    *,
    annotations: Dict[str, Any],
    output_schema: Optional[Dict[str, Any]] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> MCPTool:
    return MCPTool(
        name=name,
        description=description,
        inputSchema={
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
        annotations=annotations,
        outputSchema=output_schema,
        meta=meta,
    )


def _json_result(payload: Any, summary: Optional[str] = None) -> Dict[str, Any]:
    text = summary if summary is not None else json.dumps(payload, indent=2, ensure_ascii=False)
    return {
        "content": [{"type": "text", "text": text}],
        "metadata": payload if isinstance(payload, dict) else {"result": payload},
    }


# ---------------------------------------------------------------------------
# Tool handlers (lazy imports to keep registry import light)
# ---------------------------------------------------------------------------


async def _handle_mcp_apps_smoke(**_kwargs: Any) -> Dict[str, Any]:
    payload = {
        "ok": True,
        "message": "Ziksaka MCP Apps transport is live.",
        "ui": ui_uri("smoke"),
    }
    return _json_result(payload, summary="MCP Apps smoke: transport OK")


async def _handle_prep_card(
    entity: str, scope: str = "work", since: Optional[str] = None
) -> Dict[str, Any]:
    from .composers.prep_card import compose_prep_card

    payload = await compose_prep_card(entity=entity, scope=scope, since=since)
    name = payload.get("entity", {}).get("name") or entity
    band = (payload.get("staleness") or {}).get("band")
    summary = f"Prep card for {name}" + (f" ({band})" if band else "")
    return _json_result(payload, summary=summary)


async def _handle_prep_card_expand(
    entity: str, scope: str = "work", hops: int = 1, token_budget: int = 4000
) -> Dict[str, Any]:
    from .composers.prep_card import compose_prep_card_expand

    payload = await compose_prep_card_expand(
        entity=entity, scope=scope, hops=hops, token_budget=token_budget
    )
    return _json_result(payload, summary=f"Expanded context for {entity}")


async def _handle_prep_card_timeline(
    entity: str,
    scope: str = "work",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> Dict[str, Any]:
    from .composers.prep_card import compose_prep_card_timeline

    payload = await compose_prep_card_timeline(
        entity=entity, scope=scope, from_date=from_date, to_date=to_date
    )
    n = len(payload.get("items") or [])
    return _json_result(payload, summary=f"Timeline for {entity}: {n} items")


async def _handle_lint_queue(
    scope: str, categories: Optional[List[str]] = None
) -> Dict[str, Any]:
    from .composers.lint_queue import compose_lint_queue

    payload = await compose_lint_queue(scope=scope, categories=categories)
    n = len(payload.get("findings") or [])
    return _json_result(payload, summary=f"Lint queue ({scope}): {n} findings")


async def _handle_lint_apply(scope: str, finding_ids: List[str]) -> Dict[str, Any]:
    from .orchestrators.lint_apply import apply_lint_findings

    payload = await apply_lint_findings(scope=scope, finding_ids=finding_ids)
    applied = len(payload.get("applied") or [])
    return _json_result(payload, summary=f"Lint apply: {applied} applied")


async def _handle_snapshot_grid(
    org_id: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    scope: str = "work",
) -> Dict[str, Any]:
    from .composers.snapshot_grid import compose_snapshot_grid

    payload = await compose_snapshot_grid(
        org_id=org_id, from_date=from_date, to_date=to_date, scope=scope
    )
    n = len(payload.get("orgs") or [])
    return _json_result(payload, summary=f"Snapshot grid: {n} orgs")


async def _handle_snapshot_save(rows: List[Dict[str, Any]], scope: str = "work") -> Dict[str, Any]:
    from .orchestrators.snapshot_save import save_snapshots

    payload = await save_snapshots(rows=rows, scope=scope)
    ok = sum(1 for r in (payload.get("results") or []) if r.get("ok"))
    return _json_result(payload, summary=f"Snapshot save: {ok} ok")


async def _handle_debrief_form(
    customer: Optional[str] = None,
    date: Optional[str] = None,
    engagement_type: Optional[str] = None,
    scope: str = "work",
) -> Dict[str, Any]:
    from .composers.debrief import compose_debrief_form

    payload = await compose_debrief_form(
        customer=customer,
        date=date,
        engagement_type=engagement_type,
        scope=scope,
    )
    return _json_result(payload, summary="Debrief form ready")


async def _handle_debrief_preview(
    payload: Dict[str, Any], scope: str = "work"
) -> Dict[str, Any]:
    from .orchestrators.debrief import preview_debrief

    result = await preview_debrief(payload=payload, scope=scope)
    n = len(result.get("writes") or [])
    return _json_result(result, summary=f"Debrief preview: {n} writes planned")


async def _handle_debrief_submit(
    payload: Dict[str, Any],
    idempotency_key: str,
    scope: str = "work",
) -> Dict[str, Any]:
    from .orchestrators.debrief import submit_debrief

    result = await submit_debrief(
        payload=payload, idempotency_key=idempotency_key, scope=scope
    )
    written = len(result.get("written") or [])
    return _json_result(result, summary=f"Debrief submit: {written} written")


async def _handle_triage_board(limit: int = 50) -> Dict[str, Any]:
    from .composers.triage import compose_triage_board

    payload = await compose_triage_board(limit=limit)
    total = (payload.get("counts") or {}).get("total", 0)
    return _json_result(payload, summary=f"Triage board: {total} inbox items")


async def _handle_promote_capture(
    path: str,
    scope: str,
    target_folder: str,
    target_type: str,
    title: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    from .orchestrators.triage import promote_capture

    result = await promote_capture(
        path=path,
        scope=scope,
        target_folder=target_folder,
        target_type=target_type,
        title=title,
        tags=tags,
    )
    return _json_result(result, summary=f"Promoted to {result.get('new_path')}")


async def _handle_archive_capture(path: str) -> Dict[str, Any]:
    from .orchestrators.triage import archive_capture

    result = await archive_capture(path=path)
    return _json_result(result, summary=f"Archived to {result.get('new_path')}")


_APP_DISPATCH: Dict[str, Handler] = {
    "mcp_apps_smoke": _handle_mcp_apps_smoke,
    "prep_card": _handle_prep_card,
    "prep_card_expand": _handle_prep_card_expand,
    "prep_card_timeline": _handle_prep_card_timeline,
    "lint_queue": _handle_lint_queue,
    "lint_apply": _handle_lint_apply,
    "snapshot_grid": _handle_snapshot_grid,
    "snapshot_save": _handle_snapshot_save,
    "debrief_form": _handle_debrief_form,
    "debrief_preview": _handle_debrief_preview,
    "debrief_submit": _handle_debrief_submit,
    "triage_board": _handle_triage_board,
    "promote_capture": _handle_promote_capture,
    "archive_capture": _handle_archive_capture,
}

APP_TOOL_NAMES = frozenset(_APP_DISPATCH.keys())


def get_app_tools() -> List[MCPTool]:
    """Register all MCP App tools (model-visible + app-only)."""
    read_only = {
        "title": "",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
    write_ann = {
        "title": "",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    }
    idempotent_write = {
        "title": "",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }

    tools: List[MCPTool] = [
        _tool(
            "mcp_apps_smoke",
            "Smoke-test MCP Apps transport. Returns a small structured payload "
            "and renders the smoke UI when the host supports MCP Apps.",
            {},
            [],
            annotations={**read_only, "title": "MCP Apps Smoke"},
            output_schema={
                "type": "object",
                "properties": {
                    "ok": {"type": "boolean"},
                    "message": {"type": "string"},
                    "ui": {"type": "string"},
                },
            },
            meta=_ui_meta(ui_uri("smoke"), visibility=["model", "app"]),
        ),
        _tool(
            "prep_card",
            "Meeting prep card for one entity: resolution, staleness, open questions, "
            "commitments, connections, recent timeline, and gaps. Prefer this over a "
            "raw get_dossier dump when Franklin asks what he has on a customer/person "
            "before a call.",
            {
                "entity": {"type": "string", "description": "Entity name or alias"},
                "scope": {
                    "type": "string",
                    "enum": ["personal", "passion", "work"],
                    "description": "Workspace scope (required; never inferred)",
                    "default": "work",
                },
                "since": {
                    "type": "string",
                    "description": "Optional YYYY-MM-DD lower bound for recent activity",
                },
            },
            ["entity"],
            annotations={**read_only, "title": "Prep Card"},
            output_schema={"type": "object"},
            meta=_ui_meta(ui_uri("prep-card"), visibility=["model", "app"]),
        ),
        _tool(
            "prep_card_expand",
            "App-only: expand prep card with build_context (token-budgeted).",
            {
                "entity": {"type": "string"},
                "scope": {"type": "string", "enum": ["personal", "passion", "work"]},
                "hops": {"type": "integer", "minimum": 1, "maximum": 3, "default": 1},
                "token_budget": {"type": "integer", "default": 4000},
            },
            ["entity", "scope"],
            annotations={**read_only, "title": "Prep Card Expand"},
            output_schema={"type": "object"},
            meta={"ui": {"visibility": ["app"]}},
        ),
        _tool(
            "prep_card_timeline",
            "App-only: full interaction timeline for an entity (replaces Recent panel).",
            {
                "entity": {"type": "string"},
                "scope": {"type": "string", "enum": ["personal", "passion", "work"]},
                "from_date": {"type": "string", "description": "YYYY-MM-DD"},
                "to_date": {"type": "string", "description": "YYYY-MM-DD"},
            },
            ["entity", "scope"],
            annotations={**read_only, "title": "Prep Card Timeline"},
            output_schema={"type": "object"},
            meta={"ui": {"visibility": ["app"]}},
        ),
        _tool(
            "lint_queue",
            "Convention drift as an approvable checklist. Calls lint_vault(fix=False) "
            "and graph_health; never auto-fixes.",
            {
                "scope": {"type": "string", "enum": ["personal", "passion", "work"]},
                "categories": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional category filter",
                },
            },
            ["scope"],
            annotations={**read_only, "title": "Lint Queue"},
            output_schema={"type": "object"},
            meta=_ui_meta(ui_uri("lint-queue"), visibility=["model", "app"]),
        ),
        _tool(
            "lint_apply",
            "App-only: apply selected lint findings by id after user approval. "
            "Re-lints server-side; returns applied/skipped/stale.",
            {
                "scope": {"type": "string", "enum": ["personal", "passion", "work"]},
                "finding_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                },
            },
            ["scope", "finding_ids"],
            annotations={**write_ann, "title": "Lint Apply"},
            output_schema={"type": "object"},
            meta={"ui": {"visibility": ["app"]}},
        ),
        _tool(
            "snapshot_grid",
            "Impact snapshot grid for engagements (work scope only). Shows "
            "-30/0/+30/+90 windows vs _snapshots/ with 14-day tolerance.",
            {
                "org_id": {"type": "string"},
                "from_date": {"type": "string", "description": "YYYY-MM-DD"},
                "to_date": {"type": "string", "description": "YYYY-MM-DD"},
                "scope": {"type": "string", "enum": ["work"], "default": "work"},
            },
            [],
            annotations={**read_only, "title": "Snapshot Grid"},
            output_schema={"type": "object"},
            meta=_ui_meta(ui_uri("snapshot-entry"), visibility=["model", "app"]),
        ),
        _tool(
            "snapshot_save",
            "App-only: save snapshot rows via capture_snapshot after preview approval.",
            {
                "rows": {
                    "type": "array",
                    "items": {"type": "object"},
                    "minItems": 1,
                },
                "scope": {"type": "string", "enum": ["work"], "default": "work"},
            },
            ["rows"],
            annotations={**idempotent_write, "title": "Snapshot Save"},
            output_schema={"type": "object"},
            meta={"ui": {"visibility": ["app"]}},
        ),
        _tool(
            "debrief_form",
            "Post-call debrief form prefill: entity gaps, parent engagements, "
            "ontology vocab. Work scope only.",
            {
                "customer": {"type": "string"},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "engagement_type": {"type": "string"},
                "scope": {"type": "string", "enum": ["work"], "default": "work"},
            },
            [],
            annotations={**read_only, "title": "Debrief Form"},
            output_schema={"type": "object"},
            meta=_ui_meta(ui_uri("debrief-form"), visibility=["model", "app"]),
        ),
        _tool(
            "debrief_preview",
            "App-only: return the exact write plan for a debrief payload.",
            {
                "payload": {"type": "object"},
                "scope": {"type": "string", "enum": ["work"], "default": "work"},
            },
            ["payload"],
            annotations={**read_only, "title": "Debrief Preview"},
            output_schema={"type": "object"},
            meta={"ui": {"visibility": ["app"]}},
        ),
        _tool(
            "debrief_submit",
            "App-only: execute debrief writes with idempotency_key. Partial failure "
            "reports written vs failed; no rollback.",
            {
                "payload": {"type": "object"},
                "idempotency_key": {"type": "string"},
                "scope": {"type": "string", "enum": ["work"], "default": "work"},
            },
            ["payload", "idempotency_key"],
            annotations={**idempotent_write, "title": "Debrief Submit"},
            output_schema={"type": "object"},
            meta={"ui": {"visibility": ["app"]}},
        ),
        _tool(
            "triage_board",
            "Inbox triage for root 01_seeds/ captures with status: inbox. "
            "One-card mobile-first queue.",
            {
                "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
            },
            [],
            annotations={**read_only, "title": "Triage Board"},
            output_schema={"type": "object"},
            meta=_ui_meta(ui_uri("triage-board"), visibility=["model", "app"]),
        ),
        _tool(
            "promote_capture",
            "First-class vault primitive: promote a root 01_seeds/ capture into a "
            "scoped folder (01_seeds / 04_resources / 05_knowledge), rewriting "
            "frontmatter from type:capture to the target type. Preserves body links.",
            {
                "path": {
                    "type": "string",
                    "description": "Vault-root path e.g. 01_seeds/2026-07-31-….md",
                },
                "scope": {"type": "string", "enum": ["personal", "passion", "work"]},
                "target_folder": {
                    "type": "string",
                    "enum": ["01_seeds", "04_resources", "05_knowledge"],
                },
                "target_type": {
                    "type": "string",
                    "enum": ["seed", "resource", "knowledge"],
                },
                "title": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            ["path", "scope", "target_folder", "target_type"],
            annotations={**write_ann, "title": "Promote Capture"},
            output_schema={"type": "object"},
            # Model-visible: first-class vault primitive, not app-only.
            meta={"ui": {"visibility": ["model", "app"]}},
        ),
        _tool(
            "archive_capture",
            "App-only: move a root capture to 99_archive/ (never hard delete).",
            {
                "path": {"type": "string"},
            },
            ["path"],
            annotations={**write_ann, "title": "Archive Capture"},
            output_schema={"type": "object"},
            meta={"ui": {"visibility": ["app"]}},
        ),
    ]
    return tools


async def execute_app_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch an MCP App tool call."""
    handler = _APP_DISPATCH.get(tool_name)
    if handler is None:
        raise ValueError(f"Unknown app tool: {tool_name}")
    args = dict(arguments or {})
    # Map JSON `from`/`to` aliases if clients send them
    if "from" in args and "from_date" not in args:
        args["from_date"] = args.pop("from")
    if "to" in args and "to_date" not in args:
        args["to_date"] = args.pop("to")
    try:
        return await handler(**args)
    except TypeError as e:
        raise ValueError(f"Invalid arguments for tool '{tool_name}': {e}") from e
