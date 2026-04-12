# Workspace Rework — Implementation Summary

This document summarizes **Phase 2 (MCP server)** of the workspace-aware vault design described in [`WORKSPACE_REWORK_DESIGN.m`](WORKSPACE_REWORK_DESIGN.m). Vault file cleanup (Phase 1) and Claude skill updates (Phase 3) are separate.

## Goals

- Enforce **workspace scoping** from the API key / OAuth client (connection-level), not from trust in agent-supplied paths alone.
- Expose **canonical tool names** without the `obs_` prefix while keeping **`obs_*` aliases** during migration.
- Remove broken tools: **`obs_search_notes`**, **`obs_execute_command`**.
- Fix **recursive note counts** in vault structure and add **scope-aware** listing, search, journal, and templates.

## Architecture

1. **`WorkspaceContext`** is produced in [`src/auth.py`](../src/auth.py) after validating the Bearer token (workspace key file, static `MCP_API_KEY`, or OAuth access token + `oauth_clients` map).
2. A **`contextvars`** slot ([`src/scope.py`](../src/scope.py) — `workspace_ctx`) is set in [`main.py`](../main.py) for each `POST /mcp` request so tool handlers read the same scopes without threading `Request` through the MCP stack.
3. Tools resolve vault paths as **`{scope}/{agent-relative-path}`**, validate traversal and forbidden leading workspace segments, and return **workspace-relative paths** plus a **`scope`** field in structured metadata where applicable.

## Configuration

| Mechanism | Purpose |
|-----------|---------|
| [`workspace_keys.json`](../workspace_keys.json.example) (path via `WORKSPACE_KEYS_PATH`) | Maps raw bearer secrets under `keys` and OAuth `client_id` under `oauth_clients` to `scopes` and `role`. |
| `MCP_DEFAULT_WORKSPACE_SCOPES` | Comma-separated fallback when a token/client has no explicit entry (default: `personal,passion,work`). |
| `MCP_API_KEY` | If it matches a key in `keys`, uses that entry; otherwise gets default scopes (backward compatible). |

## Tool surface

- **New / canonical:** `workspaces`, `vault_structure`, `list_notes`, `list_journal`, `search`, `read_note`, `create_note`, `update_note`, `append_note`, `note_exists`, `delete_note`.
- **Aliases:** Parallel `obs_*` names for the same handlers (except removed tools).
- **`workspaces`:** Returns allowed scopes and role for the current key (no Obsidian I/O).
- **`scope` parameter:** Optional on reads (narrows or uses all allowed scopes); **required on writes when the key has more than one scope** (enforced in code).

## Key files

| File | Role |
|------|------|
| [`src/scope.py`](../src/scope.py) | Scope helpers + `workspace_ctx`. |
| [`src/auth.py`](../src/auth.py) | Load workspace keys; return `WorkspaceContext`. |
| [`main.py`](../main.py) | Set/reset `workspace_ctx` around MCP handling. |
| [`src/tools/obsidian_tools.py`](../src/tools/obsidian_tools.py) | Tool definitions, scoping logic, `OBSIDIAN_ROUTED_TOOL_NAMES`. |
| [`src/mcp_server.py`](../src/mcp_server.py) | Route tool calls by routed-name set. |
| [`src/clients/obsidian_client.py`](../src/clients/obsidian_client.py) | Recursive folder note counts; skip `.obsidian` in scans. |
| [`src/utils/template_utils.py`](../src/utils/template_utils.py) | `workspace_scope` prefix for vault template paths. |

## Operational assumptions

- The vault is expected to use top-level folders **`personal/`**, **`passion/`**, **`work/`** so server-built paths align with the filesystem.
- OAuth clients from dynamic registration should be listed under `oauth_clients` if they must not receive the full default scope list.

## MCP prompts & resources (agent context)

- **Prompt `vault_mcp_agent_guide`** — Canonical instructions for workspaces, tool choice, `scope`, paths, and resources vs tools ([`src/prompts/obsidian_prompts.py`](../src/prompts/obsidian_prompts.py)).
- Template prompts reference workspace-relative MCP paths and point to that guide.
- Resource listings add workspace hints in descriptions; root description notes resources are not scope-filtered ([`src/resources/obsidian_resources.py`](../src/resources/obsidian_resources.py)).

## Testing

- [`tests/test_workspace_scope.py`](../tests/test_workspace_scope.py) — Scope helpers, template prefix, auth JSON sample, routed tool set.
- [`pytest.ini`](../pytest.ini) — `asyncio_mode = auto` for existing async integration-style tests.
- Integration scripts under `tests/` and [`verify_tools.py`](../verify_tools.py) were updated for the new tool names and counts.

## Related design doc

- [`docs/WORKSPACE_REWORK_DESIGN.m`](WORKSPACE_REWORK_DESIGN.m) — Full product/design specification (scopes, skills, future knowledge graph).
