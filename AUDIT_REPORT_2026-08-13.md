# MCP Server Audit — 2026-08-13

Full audit of tools, access control, recent updates, and performance for `obsidian-mcp-server` (live at `mcp.ziksaka.com`). Scope: tool/resource inventory, auth/security review, recent commit regression review, test suite, live smoke test against production, performance pass.

## Summary

44 tools / 14 resources / 7 prompts, all registered and reachable. 227 tests passing. One critical security issue found and fixed (credential logging), plus three smaller hardening fixes. No regressions found in recent history. Performance is healthy.

## Fixed automatically (critical/high, low-risk, verified live)

| Severity | Issue | Fix |
|---|---|---|
| **Critical** | Full OAuth/API bearer tokens were printed unredacted to stdout on every `/mcp` request, captured permanently by `journalctl` (`main.py:527`, `src/auth.py`) | Added `redact_sensitive_headers()` in `src/auth.py`; all header-logging now masks `authorization`/`x-api-key`/cookies. Verified post-restart: 9/9 new log lines redacted, 0 contain `Bearer`. |
| High | Static `MCP_API_KEY` compared with plain `==` (timing side-channel) | Switched to `hmac.compare_digest` |
| Medium | `/mcp/debug` endpoint was unauthenticated, leaking tool count/server info | Now requires the same `verify_api_key` auth as everything else |
| Cosmetic | `meeting_prep_workflow` prompt fell back to a generic description in `prompts/get` | Added its proper description in `_PROMPTS_GET_DESCRIPTIONS` |

All 227 tests pass after the changes. `obsidian-mcp.service` was restarted and re-verified against production via `scripts/verify_remote_mcp_tools.py` — all 8 read-only tool calls, `resources/list` (14), and `prompts/list` (7) succeed.

## Findings — everything else checked and found healthy

- **Tool inventory**: 44 tools all registered and reachable, no orphaned/dead code, `test_tool_registry_contract.py` enforces the count.
  - CRUD/core: `workspaces`, `vault_structure`, `list_notes`, `list_journal`, `search`, `read_note`, `create_note`, `update_note`, `append_note`, `note_exists`, `delete_note`, `rename_note`
  - Entity/graph intelligence: `resolve_entity`, `query_frontmatter`, `get_dossier`, `lint_vault`, `get_backlinks`, `get_neighbors`, `find_path`, `graph_health`, `timeline`, `last_touch`, `build_context`
  - Engagement/impact/capture: `capture`, `create_event`, `create_engagement`, `capture_snapshot`, `engagement_delta`, `impact_rollup`
  - MCP Apps/UI: `mcp_apps_smoke`, `prep_card` (+`_expand`, `_timeline`), `lint_queue`/`lint_apply`, `snapshot_grid`/`snapshot_save`, `debrief_form`/`_preview`/`_submit`, `triage_board`, `promote_capture`/`archive_capture`
  - Resources: vault root + one entry per allowed workspace (personal/passion/work/parallax) + 6 UI app resources, scope-filtered per API key
  - Prompts (7): `vault_mcp_agent_guide`, `note_template_system`, `daily_note_template`, `project_note_template`, `area_note_template`, `format_preservation_rules`, `meeting_prep_workflow`

- **Recent commits** (last 8: parallax rollout, observability, MCP Apps transport): no regressions. Parallax scope was wired consistently everywhere via `KNOWN_SCOPES` as single source of truth. The observability session-id fix was a real root-cause fix (SHA-256 hashing the fallback identity, not a masked try/except). Tool-call logging is genuinely async — `queue.put_nowait` on the request path, actual SQLite write batched via `run_in_executor` — and redacts args to `{key: type}` by default. Every commit reviewed added/extended matching tests.

- **Secrets hygiene**: `.env`, `workspace_keys.json`, `tokens.db`, `observability.db` all gitignored and confirmed untracked. `token_store.py` uses fully parameterized SQL (no injection risk), auth codes are single-use + TTL'd, refresh tokens rotate correctly, PKCE S256 verification is correct.

- **Path traversal**: all write tools (`create_note`, `update_note`, `append_note`, `delete_note`, `rename_note`) route through `src/scope.py:resolve_scoped_path`, which rejects `..` segments before touching the filesystem. No exploitable traversal today.

- **Performance**: ~60–75ms round-trip latency including HTTPS/nginx proxy hop, instant startup, ~35MB RSS, mtime-keyed corpus caching (`src/vault_intelligence/corpus.py`) avoids re-parsing unchanged notes, async SQLite writes for observability keep logging off the request path.

## Suggestions (not fixed — left for a deliberate call)

1. **No rate limiting** on `/mcp`, `/token`, `/authorize`. Token entropy (32-byte `secrets.token_urlsafe`) makes brute force impractical but isn't a substitute for throttling on an internet-facing endpoint — add an Nginx Proxy Manager rate-limit rule or `slowapi`.
2. **Raw request-body debug logging** (`main.py:528`) still prints full JSON-RPC bodies unconditionally; for write tools this can push real vault note content into the systemd journal. Consider gating behind an `MCP_DEBUG_LOG=true` env flag.
3. **No structured logging framework** — everything is `print()` to stdout with no level control. Moving to Python `logging` would let debug output be disabled in prod without code edits, and reduces the risk of a future credential-logging repeat.
4. `src/vault_intelligence/corpus.py`'s `_resolve_full_path` trusts callers to have already validated `..`; no independent check at that layer. Not exploitable today (all call sites correct) but worth a defense-in-depth assertion if new tools are added later.

## Files changed

- `main.py` — redact headers before logging; gate `/mcp/debug` behind auth
- `src/auth.py` — add `redact_sensitive_headers()`, use `hmac.compare_digest` for static key check, stop logging token prefixes
- `src/mcp_server.py` — add missing `meeting_prep_workflow` prompt description
