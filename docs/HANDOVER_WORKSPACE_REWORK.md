# Handover: Workspace-scoped MCP rework

This document is for whoever deploys, operates, or extends the Obsidian MCP server after the **workspace rework** (API key → allowed `personal` / `passion` / `work` folders, renamed tools, removed broken tools).

**Related docs**

- Design: [`WORKSPACE_REWORK_DESIGN.m`](WORKSPACE_REWORK_DESIGN.m) or [`WORKSPACE_REWORK_DESIGN.md`](WORKSPACE_REWORK_DESIGN.md) (same content may exist in either form)
- Implementation summary: [`WORKSPACE_REWORK_IMPLEMENTATION_SUMMARY.md`](WORKSPACE_REWORK_IMPLEMENTATION_SUMMARY.md)

---

## 1. What changed (high level)

| Area | Change |
|------|--------|
| **Auth** | Successful login yields a **`WorkspaceContext`** (allowed scopes + role), not just a string identity. |
| **Request scope** | FastAPI sets a **`contextvars`** token per `POST /mcp` so every tool sees the same scopes for that request. |
| **Paths** | Agents pass paths **relative to a workspace** (e.g. `06_daily-notes/2026-04-11.md`). The server prefixes `personal/`, `passion/`, or `work/`. Agents must **not** put the workspace name as the first path segment; use the **`scope`** argument instead. |
| **Writes** | If a key has **more than one** allowed scope, **`scope` is required** on create/update/append/delete. Single-scope keys auto-select that scope. |
| **Reads** | Optional **`scope`** narrows; omitted means “all scopes this key may access.” |
| **Tools removed** | `obs_search_notes`, `obs_execute_command` (broken / out of scope for workspace safety). |
| **Tools added / renamed** | Canonical names without `obs_` (aliases kept). New **`workspaces`** tool lists scopes for the current key. |
| **Obsidian client** | Vault folder **note counts** are **recursive**; `.obsidian` paths skipped in filesystem scans. |
| **Templates** | Vault templates resolve under **`{scope}/00_system/templates/...`** when applying templates on create. |

---

## 2. Files added

| File | Purpose |
|------|---------|
| [`src/scope.py`](../src/scope.py) | Scope helpers + `workspace_ctx` `ContextVar`. |
| [`workspace_keys.json.example`](../workspace_keys.json.example) | Example key → scopes + `oauth_clients` map. |
| [`pytest.ini`](../pytest.ini) | `asyncio_mode = auto` for tests. |
| [`tests/test_workspace_scope.py`](../tests/test_workspace_scope.py) | Unit tests for scope + sample auth JSON. |
| [`docs/WORKSPACE_REWORK_IMPLEMENTATION_SUMMARY.md`](WORKSPACE_REWORK_IMPLEMENTATION_SUMMARY.md) | Short technical summary. |
| [`docs/HANDOVER_WORKSPACE_REWORK.md`](HANDOVER_WORKSPACE_REWORK.md) | This handover. |

---

## 3. Files modified (main)

| File | What to know |
|------|----------------|
| [`main.py`](../main.py) | Sets/resets `workspace_ctx` around MCP handling on `POST /mcp`. |
| [`src/auth.py`](../src/auth.py) | Loads `workspace_keys.json`; returns `WorkspaceContext`; `clear_workspace_config_cache()` for tests. |
| [`src/mcp_server.py`](../src/mcp_server.py) | Routes tool calls via `OBSIDIAN_ROUTED_TOOL_NAMES` (not only `obs_` prefix). |
| [`src/tools/obsidian_tools.py`](../src/tools/obsidian_tools.py) | All tool definitions, scoping behavior, `OBSIDIAN_ROUTED_TOOL_NAMES`. |
| [`src/clients/obsidian_client.py`](../src/clients/obsidian_client.py) | Recursive counts; `.obsidian` filter. |
| [`src/utils/template_utils.py`](../src/utils/template_utils.py) | `get_template_path_for_folder(..., workspace_scope=...)`. |
| [`.env.example`](../.env.example) | `WORKSPACE_KEYS_PATH`, `MCP_DEFAULT_WORKSPACE_SCOPES`. |
| [`requirements.txt`](../requirements.txt) | `pytest-asyncio>=0.24.0`. |
| [`verify_tools.py`](../verify_tools.py) | Expected tool list updated. |
| [`tests/test_multi_app.py`](../tests/test_multi_app.py), [`tests/test_obsidian_tools_comprehensive.py`](../tests/test_obsidian_tools_comprehensive.py), [`tests/test_obsidian_tools.py`](../tests/test_obsidian_tools.py), [`tests/validate_all_tools.py`](../tests/validate_all_tools.py) | Aligned with new tools and messages. |

---

## 4. Configuration checklist (server / VPS)

### Environment variables

- **`OBSIDIAN_API_URL`**, **`OBSIDIAN_API_KEY`**, **`OBSIDIAN_VAULT_PATH`** — unchanged; vault root should contain workspace folders `personal/`, `passion/`, `work/` as in the design.
- **`MCP_API_KEY`** — still valid; if that exact string is **not** listed under `keys` in `workspace_keys.json`, the key receives **`MCP_DEFAULT_WORKSPACE_SCOPES`** (default all three).
- **`WORKSPACE_KEYS_PATH`** — path to JSON (default `workspace_keys.json` in cwd).
- **`MCP_DEFAULT_WORKSPACE_SCOPES`** — e.g. `personal,passion,work` for OAuth clients or static keys without an explicit row.
- **`MCP_BASE_URL`**, **`TOKEN_DB_PATH`** — unchanged for OAuth discovery and token store.

### `workspace_keys.json` shape

Copy from [`workspace_keys.json.example`](../workspace_keys.json.example):

- **`keys`**: map of **full bearer secret string** → `{ "name", "scopes": [...], "role" }`.
- **`oauth_clients`**: map of **`client_id`** (from OAuth dynamic registration) → same shape, for Claude.ai / other OAuth clients.

After editing keys, restart the server (config is loaded once per process unless you add reload logic).

---

## 5. Tool inventory (post-rework)

**MCP `tools/list` total:** **22** tools = **`ping`** + **21** Obsidian-registered tools (canonical + `obs_*` aliases).

**Canonical names (preferred in new skills)**

| Tool | Notes |
|------|--------|
| `workspaces` | No args; returns allowed scopes for this connection. |
| `vault_structure` | Optional `scope`, `use_cache`. |
| `list_notes` | Optional `folder`, `scope`. |
| `list_journal` | `startDate`, `endDate`; optional `scope`. |
| `search` | `keyword`; optional `folder`, `scope`, `limit`, `case_sensitive`. |
| `read_note` | `path`; optional `scope`. |
| `create_note` | `path`, `content`; **`scope` required if multi-scope key**; template flags unchanged. |
| `update_note` | `path`, `content`; optional `scope` (required if multi-scope). |
| `append_note` | Same pattern as update. |
| `note_exists` | `path`; optional `scope`. |
| `delete_note` | `path`; optional `scope` (required if multi-scope). |

**Aliases:** each of the above (except `workspaces`) has a parallel `obs_*` name for backward compatibility (e.g. `obs_keyword_search` → `search`).

**Removed from MCP:** `obs_search_notes`, `obs_execute_command`.

---

## 6. MCP prompts & resources (agent context)

**Canonical agent summary:** MCP prompt **`vault_mcp_agent_guide`** ([`src/prompts/obsidian_prompts.py`](../src/prompts/obsidian_prompts.py)) — workspaces, tool-selection table, `scope` / path rules, removed tools, and **resources vs tools** (resources are **not** API-key scope filtered).

**Other prompts** (`note_template_system`, daily/project/area templates, `format_preservation_rules`) now state that MCP paths are **workspace-relative** and point to `vault_mcp_agent_guide` where needed.

**Resources** ([`src/resources/obsidian_resources.py`](../src/resources/obsidian_resources.py)): descriptions tag **`Workspace \`personal\``** (etc.) when paths live under a known scope; vault root description warns restricted keys to prefer **tools** with **`scope`**.

**Server metadata** ([`src/mcp_server.py`](../src/mcp_server.py) `serverInfo.description`): mentions workspace-scoped tools and the prompt name for discovery.

**Maintenance rule:** When tool names or scope behavior change, update **`vault_mcp_agent_guide`** first, then skim template prompts for stale path wording.

---

## 7. Claude skill configuration

Skill **content** (Phase 3 in the design) is **not** stored in this repository by default. The design specifies **two** skills; implement them in your Cursor/Claude skill packs or internal repo:

1. **`franklin-obsidian-vault`** — Personal Claude: describes **all three** workspaces, **`scope`** usage, new tool names, routing rules (when to use `personal` vs `passion` vs `work`). See design § “Skill 1”.
2. **`franklin-work-vault`** — Work-only Claude: **only `work`**, no mention of other workspaces. See design § “Skill 2”.

### 7.1 What skills must teach the model

- Call **`workspaces`** once per session (or when unsure) to see allowed scopes for **this** connector.
- Use **canonical tool names** (`search`, `read_note`, …); aliases still work if old prompts reference `obs_*`.
- **Never** put `personal/`, `passion/`, or `work/` as the first segment of `path`; use **`scope`**.
- For **multi-scope** keys, always pass **`scope`** on **writes**.
- On reads, **omit `scope`** to search/list across allowed workspaces, or set **`scope`** to narrow.
- Keep skill prose aligned with MCP prompt **`vault_mcp_agent_guide`**, or tell the model to fetch it with `prompts/get`.

### 7.2 Claude.ai (remote MCP / OAuth)

- Connector URL: your public MCP base, e.g. `https://<your-domain>/mcp`.
- Claude uses OAuth against this server’s documented endpoints (`/.well-known/...`, `/authorize`, `/token`, etc.).
- **Important:** register each OAuth **`client_id`** under **`oauth_clients`** in `workspace_keys.json` with the right **`scopes`** (or rely on `MCP_DEFAULT_WORKSPACE_SCOPES` until configured).

### 7.3 Claude Desktop — remote connector

Same URL as Claude.ai where the product supports custom remote MCP. Ensure **Authorization** (Bearer) or proxy-injected key matches a row in **`keys`** or **`MCP_API_KEY`** behavior above.

Legacy doc (tool count and names are **out of date** but transport still valid): [`docs/claude/CLAUDE_REMOTE_CONNECTOR_SETUP.md`](claude/CLAUDE_REMOTE_CONNECTOR_SETUP.md).

### 7.4 Claude Desktop — stdio bridge

Bridge script: [`scripts/mcp_stdio_bridge.py`](../scripts/mcp_stdio_bridge.py). It forwards JSON-RPC to **`MCP_SERVER_URL`** and sends **`MCP_API_KEY`** as Bearer.

Example `claude_desktop_config.json` fragment:

```json
{
  "mcpServers": {
    "obsidian-vault": {
      "command": "/path/to/venv/bin/python",
      "args": ["/path/to/obsidian-mcp-server/scripts/mcp_stdio_bridge.py"],
      "env": {
        "MCP_SERVER_URL": "https://your-host/mcp",
        "MCP_API_KEY": "your-key-or-sk_*_from_workspace_keys"
      }
    }
  }
}
```

Use a key whose **`keys`** entry in `workspace_keys.json` matches the intended **scopes** (personal+passion vs work-only, etc.).

Detailed stdio steps: [`docs/claude/CLAUDE_DESKTOP_STDIO_SETUP.md`](claude/CLAUDE_DESKTOP_STDIO_SETUP.md) (update tool counts/names mentally to match §5 above).

### 7.5 Cursor / other “skills”

If you use Cursor **Rules** or **Agent Skills** (`SKILL.md`), mirror the same guidance: workspace model, **`scope`**, canonical tool names, and pointer to **`workspaces`**. Keep **work** and **personal** connectors on **separate** API keys with different `scopes` in `workspace_keys.json`.

---

## 8. Verification performed in development

- **`pytest`** — full suite green (30 tests) in CI/dev venv.
- **`verify_tools.py`** — registration, schemas, `tools/list` (22 tools), ping, unknown tool handling.

**Not** a substitute for: production smoke test with real **Obsidian REST API**, real **vault layout**, and **per-key** scope checks (work key cannot read `personal/`).

Suggested smoke test after deploy:

```bash
curl -sS -X POST "$MCP_BASE_URL/mcp" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <key-for-testing>" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"workspaces","arguments":{}}}'
```

Confirm returned scopes match that key’s row in `workspace_keys.json`.

---

## 9. Follow-ups (optional)

- Phase 1 vault cleanup (root `00_system/`, etc.) — operational, not in this repo.
- Phase 3 — author/replace the two **SKILL.md** packs and reference files listed in the design.
- Phase 4 — provision distinct keys (admin, personal, work, n8n, …) and document rotation.
- Add **mocked integration tests** for multi-scope vs single-scope deny/allow if you want CI to enforce the matrix without Obsidian.

---

*Generated for handoff; update this file when tool names or connector flows change again.*
