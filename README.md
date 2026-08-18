# Obsidian MCP Server

A Model Context Protocol (MCP) server providing AI assistants with full access to Obsidian vault operations across multiple workspace scopes (personal, work, passion).

## Status: Production

- **Endpoint**: `https://mcp.ziksaka.com/mcp`
- **Auth**: OAuth 2.0 with Dynamic Client Registration (DCR) + PKCE S256
- **Service**: systemd user service (`obsidian-mcp.service`)
- **Protocol**: MCP dual-compat (`2024-11-05` … `2026-07-28`) / JSON-RPC 2.0
- **Extensions**: MCP Apps (UI) + Tasks (async heavy vault tools)

## Tools (25 total)

Load MCP prompt **`vault_mcp_agent_guide`** (or vault `AGENTS.md`) for tool-selection workflows.

### Connectivity

| Tool | Description |
|---|---|
| `ping` | Liveness check |
| `workspaces` | List scopes allowed for this API key |

### General vault

| Tool | Description |
|---|---|
| `vault_structure` | Folder tree with recursive note counts |
| `list_notes` | List notes with mtime filters (modified_after, modified_before, rolling days/hours, limit) |
| `list_journal` | Daily notes in a date range |
| `search` | Relevance-ranked keyword search (param is `keyword`, not `query`) |
| `read_note` | Read a note by path |
| `create_note` | Create a note with optional template (scope required for multi-workspace keys) |
| `update_note` | Replace note content (preserves frontmatter for entity cards) |
| `append_note` | Append to a note |
| `note_exists` | Check note existence |
| `delete_note` | Delete a note |
| `capture` | Quick-capture to root `01_seeds/` — **no scope needed** |
| `create_event` | Create an `event` entity card + `## Events` back-refs (`scope=work`) |

### Vault intelligence (`scope=work`)

| Tool | Description |
|---|---|
| `resolve_entity` | Fuzzy entity/alias lookup — path, connections, backlinks, events |
| `query_frontmatter` | Filter by frontmatter (AND) + optional tag (max 50) |
| `get_dossier` | Meeting-prep brief; optional `since` |
| `lint_vault` | Convention drift audit; optional `fix=true` |
| `get_backlinks` | Typed inbound edges |
| `get_neighbors` | Graph traversal with depth, rel_type, direction |
| `find_path` | Shortest connection path between two entities |
| `graph_health` | Machine-readable graph health summary |
| `timeline` | Ordered interaction history |
| `last_touch` | Most recent timeline item |
| `build_context` | Token-budgeted graph-augmented context pack |

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
│   ├── entities/                # Knowledge graph: entities/{entity_type}/{slug}.md
│   │   ├── customer/  person/  partner/  company/  concept/  tool/  ...
│   │   └── event/               # Event entities — use the `create_event` tool
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
│   │   └── obsidian_tools.py   # All 24 Obsidian tool definitions + implementations
│   ├── prompts/
│   │   └── obsidian_prompts.py # MCP prompts
│   ├── clients/
│   │   └── obsidian_client.py  # Filesystem-native vault access
│   ├── utils/
│   │   ├── template_utils.py   # Template detection + application
│   │   └── list_notes_time.py  # mtime filter helpers for list_notes
│   └── vault_intelligence/     # Entity graph, dossier, lint tools
│       ├── corpus.py           # Note corpus builder
│       ├── parser.py           # Frontmatter + wikilink parser
│       └── tools.py            # Vault intelligence tool implementations
├── tests/
├── scripts/
│   └── dev-server.sh           # Local dev server manager (macOS)
└── docs/
    ├── claude/                 # Claude connector setup
    ├── deployment/             # Production setup guides
    └── ...
```

## Local Development

`scripts/dev-server.sh` manages the local server lifecycle. It creates a `.venv`, installs dependencies, and starts/stops the server in the background. It is also wired to Cursor's SessionStart/SessionEnd hooks so it starts automatically when you open the project.

```bash
git clone <repository>
cd obsidian-mcp-server

# One-time setup: creates .venv, installs deps, seeds .env from .env.example
scripts/dev-server.sh setup

# Edit .env — fill in MCP_API_KEY, OBSIDIAN_API_URL, OBSIDIAN_API_KEY, OBSIDIAN_VAULT_PATH
cp .env.example .env

# Start the server in the background (idempotent — safe to re-run)
scripts/dev-server.sh start
```

Other available commands:

```bash
scripts/dev-server.sh stop      # Gracefully stop the background server
scripts/dev-server.sh restart   # stop + start
scripts/dev-server.sh status    # Show running state and PID
scripts/dev-server.sh logs      # Tail dev-server.log
```

The server binds to `http://127.0.0.1:$MCP_PORT` (default `8000` from `.env`, overridable via `MCP_PORT` env var).

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
| `entities/event/` | `event_template.md` (falls back to a built-in event scaffold) |

The `capture` tool uses the vault capture template (`00_system/templates/capture.md`) with inline fallback. The `create_event` tool builds event cards from structured fields; other entity cards are hand-maintained.

## Documentation

- [`docs/EVENT_ENTITY_SUPPORT.md`](docs/EVENT_ENTITY_SUPPORT.md) — event entity graph support + retrieval/authoring improvements
- [`CLAUDE_CONNECTOR_DIAGNOSIS.md`](CLAUDE_CONNECTOR_DIAGNOSIS.md) — live diagnostic reference, OAuth gotchas, troubleshooting
- [`docs/claude/CLAUDE_REMOTE_CONNECTOR_SETUP.md`](docs/claude/CLAUDE_REMOTE_CONNECTOR_SETUP.md) — connector setup steps
- [`docs/deployment/`](docs/deployment/) — production deployment guides
