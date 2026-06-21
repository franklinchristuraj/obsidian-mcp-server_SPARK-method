# Obsidian MCP Server

A Model Context Protocol (MCP) server providing AI assistants with full access to Obsidian vault operations across multiple workspace scopes (personal, work, passion).

## Status: Production

- **Endpoint**: `https://mcp.ziksaka.com/mcp`
- **Auth**: OAuth 2.0 with Dynamic Client Registration (DCR) + PKCE S256
- **Service**: systemd user service (`obsidian-mcp.service`)
- **Protocol**: MCP 2024-11-05 / JSON-RPC 2.0

## Tools (17 total)

| Tool | Description |
|---|---|
| `ping` | Liveness check |
| `workspaces` | List scopes allowed for this API key |
| `vault_structure` | Folder tree with recursive note counts |
| `list_notes` | List notes with mtime filters (modified_after, modified_before, rolling days/hours, limit) |
| `list_journal` | Daily notes in a date range |
| `search` | Keyword search in note bodies |
| `read_note` | Read a note by path |
| `create_note` | Create a note with optional template (scope required for multi-workspace keys) |
| `update_note` | Replace note content |
| `append_note` | Append to a note |
| `note_exists` | Check note existence |
| `delete_note` | Delete a note |
| `resolve_entity` | Fuzzy entity lookup — returns canonical path, frontmatter, connections, backlinks |
| `query_frontmatter` | Filter notes by frontmatter key/value pairs |
| `get_dossier` | Meeting-prep brief for an entity (wraps resolve_entity + recent mentions) |
| `lint_vault` | Audit convention drift: missing frontmatter, broken wikilinks, orphan entities |
| `capture` | Quick-capture to `01_seeds/` at vault root — **no scope needed** (voice/phone capture) |

## Vault Structure

```
vault/
├── 01_seeds/          # Cross-scope inbox — use `capture` tool, no scope needed
├── personal/
│   ├── 00_system/templates/
│   ├── 01_seeds/
│   ├── 02_projects/
│   ├── 03_areas/
│   ├── 06_daily-notes/
│   └── ...
├── work/
│   ├── 00_system/templates/
│   ├── 01_seeds/
│   ├── 02_projects/
│   ├── 03_areas/
│   ├── 11_work-meeting-notes/
│   └── ...
└── passion/
    ├── 00_system/templates/
    ├── 01_seeds/
    ├── 02_projects/
    └── ...
```

## API Usage

### Authentication

OAuth 2.0 (recommended for Claude.ai) or static Bearer token:

```bash
Authorization: Bearer YOUR_API_KEY
```

### Quick-capture to seeds (no scope needed)

```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
     -H "Content-Type: application/json" \
     -X POST https://mcp.ziksaka.com/mcp \
     -d '{
       "jsonrpc": "2.0",
       "method": "tools/call",
       "params": {
         "name": "capture",
         "arguments": {
           "title": "My idea",
           "content": "Voice transcript or raw thought",
           "source": "voice"
         }
       },
       "id": 1
     }'
```

### Create a scoped note with template

```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
     -H "Content-Type: application/json" \
     -X POST https://mcp.ziksaka.com/mcp \
     -d '{
       "jsonrpc": "2.0",
       "method": "tools/call",
       "params": {
         "name": "create_note",
         "arguments": {
           "path": "02_projects/my-project.md",
           "content": "",
           "scope": "work",
           "use_template": true,
           "template_vars": {"title": "My Project"}
         }
       },
       "id": 1
     }'
```

### List tools

```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
     -H "Content-Type: application/json" \
     -X POST https://mcp.ziksaka.com/mcp \
     -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

## OAuth Flow (Claude.ai)

Claude.ai uses Dynamic Client Registration (RFC 7591):

1. Discovers `/.well-known/oauth-authorization-server` → finds `registration_endpoint`
2. Registers via `POST /register` (public client, no secret)
3. User authorises at `/authorize` with PKCE S256
4. Callback to `https://claude.ai/api/mcp/auth_callback`
5. Token via `POST /token`

**Critical:** `registration_endpoint` must be in OAuth metadata or Claude.ai never opens the browser popup.

## Project Structure

```
obsidian-mcp-server/
├── main_production.py          # Production entry point
├── main.py                     # Development entry point
├── src/
│   ├── mcp_server.py           # MCP protocol handler + tool routing
│   ├── auth.py                 # OAuth 2.0 + Bearer token middleware
│   ├── token_store.py          # SQLite-backed token/client store
│   ├── scope.py                # Workspace scope resolution
│   ├── tools/
│   │   └── obsidian_tools.py   # All 17 tool definitions + implementations
│   ├── prompts/
│   │   └── obsidian_prompts.py # MCP prompts
│   ├── clients/
│   │   └── obsidian_client.py  # Obsidian REST API wrapper
│   ├── utils/
│   │   └── template_utils.py   # Template detection + application
│   └── vault_intelligence/     # Entity graph, dossier, lint tools
├── tests/
├── scripts/
└── docs/
    ├── claude/                 # Claude connector setup
    ├── deployment/             # Production setup guides
    └── ...
```

## Local Development

```bash
git clone <repository>
cd obsidian-mcp-server
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env: MCP_API_KEY, OBSIDIAN_API_URL, OBSIDIAN_API_KEY, OBSIDIAN_VAULT_PATH

python main.py
```

## Service Management

```bash
systemctl --user status obsidian-mcp.service
systemctl --user restart obsidian-mcp.service
journalctl --user -u obsidian-mcp.service -f
```

## Template System

Templates live in each workspace's `00_system/templates/` folder. The server auto-detects the template from the note path:

| Folder | Template applied |
|---|---|
| `01_seeds/` | `seed.md` |
| `02_projects/` | `project.md` |
| `03_areas/` | `area.md` |
| `06_daily-notes/` | `daily-journal.md` |
| `11_work-meeting-notes/` | `meeting-notes.md` |

The `capture` tool uses a hardcoded generic seed template (cross-scope, no workspace needed).

## Documentation

- [`CLAUDE_CONNECTOR_DIAGNOSIS.md`](CLAUDE_CONNECTOR_DIAGNOSIS.md) — live diagnostic reference, OAuth gotchas, troubleshooting
- [`docs/claude/CLAUDE_REMOTE_CONNECTOR_SETUP.md`](docs/claude/CLAUDE_REMOTE_CONNECTOR_SETUP.md) — connector setup steps
- [`docs/deployment/`](docs/deployment/) — production deployment guides
