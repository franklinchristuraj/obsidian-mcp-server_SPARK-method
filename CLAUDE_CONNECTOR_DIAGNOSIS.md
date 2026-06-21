# Claude Connector MCP - Diagnostic Reference

**Last Updated:** 2026-06-21  
**Status:** ✅ Fully Operational

## Current State

The Obsidian MCP server is **healthy and actively serving Claude.ai** via OAuth 2.0.

| Component | Status | Details |
|---|---|---|
| Remote server | ✅ Running | `https://mcp.ziksaka.com` |
| Systemd service | ✅ Active | Running since 2026-06-10, PID 3967024 |
| OAuth (DCR) | ✅ Configured | PKCE S256, `/register`, `/authorize`, `/token` |
| Claude.ai connection | ✅ Live | Seeing `Claude-User` UA in logs with bearer tokens |
| Tools exposed | ✅ 17 tools | See list below |

---

## Quick Diagnostics

### Health Check
```bash
curl https://mcp.ziksaka.com/health
# {"status":"healthy","service":"obsidian-mcp-server"}
```

### OAuth Metadata
```bash
curl https://mcp.ziksaka.com/.well-known/oauth-authorization-server
```
Returns `registration_endpoint`, `authorization_endpoint`, `token_endpoint`, PKCE S256.

### Tools List (via API)
```bash
curl -H "Authorization: Bearer $API_KEY" \
     -H "Content-Type: application/json" \
     -X POST https://mcp.ziksaka.com/mcp \
     -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

### Service Status
```bash
systemctl --user status obsidian-mcp.service
journalctl --user -u obsidian-mcp.service -n 50 --no-pager
```

### Restart Service
```bash
systemctl --user restart obsidian-mcp.service
```

---

## Tools (16 total)

| Tool | Purpose |
|---|---|
| `ping` | Connection liveness check |
| `workspaces` | List scopes allowed for this API key |
| `vault_structure` | Folder tree with note counts |
| `list_notes` | List notes with mtime filters (modified_after, modified_before, rolling days/hours) |
| `list_journal` | Daily notes in a date range |
| `search` | Keyword search in note bodies |
| `read_note` | Read a note by path |
| `create_note` | Create a note (supports templates) |
| `update_note` | Replace note content |
| `append_note` | Append to a note |
| `note_exists` | Check note existence |
| `delete_note` | Delete a note |
| `resolve_entity` | Fuzzy entity lookup — returns canonical path, frontmatter, connections, backlinks |
| `query_frontmatter` | Filter notes by frontmatter key/value pairs |
| `get_dossier` | Meeting-prep brief for an entity (wraps resolve_entity + mentions) |
| `lint_vault` | Audit convention drift: missing frontmatter, broken wikilinks, orphan entities |
| `capture` | Quick-capture to `01_seeds/` at vault root — no scope needed (for voice/phone capture) |

---

## OAuth Flow (Claude.ai)

Claude.ai uses **Dynamic Client Registration (RFC 7591)**:

1. Claude.ai discovers `/.well-known/oauth-authorization-server`
2. Registers as a client via `POST /register` (public client, no secret)
3. User authorised via `GET /authorize?response_type=code&code_challenge=...&code_challenge_method=S256`
4. Callback to `https://claude.ai/api/mcp/auth_callback`
5. Token exchanged via `POST /token` with PKCE verifier

**Critical requirement:** `registration_endpoint` must be in the OAuth metadata or Claude.ai never opens the browser popup.

---

## Server Endpoints

| Endpoint | URL |
|---|---|
| MCP (remote) | `https://mcp.ziksaka.com/mcp` |
| MCP (local) | `http://localhost:8888/mcp` |
| Health | `https://mcp.ziksaka.com/health` |
| OAuth metadata | `https://mcp.ziksaka.com/.well-known/oauth-authorization-server` |
| OAuth register | `https://mcp.ziksaka.com/register` |
| OAuth authorize | `https://mcp.ziksaka.com/authorize` |
| OAuth token | `https://mcp.ziksaka.com/token` |
| Obsidian REST API | `http://localhost:27123` (local only) |

**Vault path:** `/home/franklinchris/obsidian/config/franklin-vault`  
**API key:** Stored in `.env` as `MCP_API_KEY` (do not commit)

---

## Known Gotchas

### FastAPI 401 exception handler
`@app.exception_handler(401)` does **not** catch `HTTPException(status_code=401)` — FastAPI's built-in handler intercepts it first. Must use `@app.exception_handler(HTTPException)` to add `WWW-Authenticate` headers.

### Tool scope parameter
Most write tools require `scope` (personal/work/passion) when the API key grants access to multiple workspaces. Read tools default to all allowed scopes.

### Nginx Proxy Manager
Server sits behind NPM at `mcp.ziksaka.com`. If the MCP endpoint returns unexpected HTML errors, check NPM proxy host config and SSL cert validity.

---

## Troubleshooting

### Claude.ai connector not connecting
1. Check OAuth metadata endpoint returns `registration_endpoint`
2. Verify service is running: `systemctl --user status obsidian-mcp.service`
3. Tail logs for auth errors: `journalctl --user -u obsidian-mcp.service -f`
4. Confirm NPM is proxying correctly: `curl https://mcp.ziksaka.com/health`

### Note creation fails
1. Verify scope matches a workspace the API key can write to
2. Check Obsidian REST API is running: `curl -H "Authorization: Bearer $OBSIDIAN_API_KEY" http://localhost:27123/vault/`
3. Confirm `OBSIDIAN_VAULT_PATH` in `.env` matches actual vault location

### Service won't start
```bash
journalctl --user -u obsidian-mcp.service -n 100 --no-pager
# Then test manually:
cd /home/franklinchris/obsidian-mcp-server
source venv/bin/activate
python3 main_production.py
```
