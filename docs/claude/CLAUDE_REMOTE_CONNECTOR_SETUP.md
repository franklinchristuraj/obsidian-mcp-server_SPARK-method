# Claude Remote Connector Setup

## Server Details

| | |
|---|---|
| MCP endpoint | `https://mcp.ziksaka.com/mcp` |
| OAuth metadata | `https://mcp.ziksaka.com/.well-known/oauth-authorization-server` |
| Tools | 17 |
| Auth | OAuth 2.0 CIMD + DCR fallback + PKCE S256 (Claude.ai) or static Bearer token |

## Claude.ai Connector (OAuth)

1. Go to **claude.ai → Settings → Connectors → Add custom connector**
2. Set **Remote MCP Server URL**: `https://mcp.ziksaka.com/mcp`
3. Leave OAuth Client ID / Secret empty
4. Click connect and complete the browser OAuth popup

Claude.ai discovers `/.well-known/oauth-authorization-server`. Preferred identity is **CIMD** (`client_id_metadata_document_supported: true`). If the client still uses Dynamic Client Registration, `registration_endpoint` remains available as a fallback.

## Claude Desktop (Bearer token)

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "obsidian": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-fetch", "https://mcp.ziksaka.com/mcp"],
      "env": {
        "BEARER_TOKEN": "YOUR_API_KEY"
      }
    }
  }
}
```

## Available Tools (17)

| Tool | Scope required? | Purpose |
|---|---|---|
| `ping` | No | Liveness check |
| `workspaces` | No | List allowed scopes |
| `capture` | **No** | Quick-capture to `01_seeds/` (voice/phone capture) |
| `vault_structure` | No | Folder tree |
| `list_notes` | No | Notes with mtime filters |
| `list_journal` | No | Daily notes by date range |
| `search` | No | Keyword search |
| `read_note` | No | Read a note |
| `create_note` | Yes (multi-workspace keys) | Create with template |
| `update_note` | Yes | Replace content |
| `append_note` | Yes | Append content |
| `note_exists` | No | Check existence |
| `delete_note` | Yes | Delete a note |
| `resolve_entity` | No | Fuzzy entity lookup |
| `query_frontmatter` | No | Filter by frontmatter |
| `get_dossier` | No | Meeting-prep brief |
| `lint_vault` | No | Audit convention drift |

Scopes: `personal`, `work`, `passion`

## Verify Connection

```bash
curl -X POST https://mcp.ziksaka.com/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

Should return 17 tools.

## Troubleshooting

**Claude.ai connector never opens auth popup**
→ Check that `/.well-known/oauth-authorization-server` includes `registration_endpoint`. Without it, DCR fails silently.

**"must pass scope" error on create_note**
→ Pass `"scope": "personal"` (or `work` / `passion`). Use `capture` instead if the note doesn't belong to a specific workspace yet.

**Service not responding**
```bash
systemctl --user status obsidian-mcp.service
journalctl --user -u obsidian-mcp.service -n 50 --no-pager
```

See [`CLAUDE_CONNECTOR_DIAGNOSIS.md`](../../CLAUDE_CONNECTOR_DIAGNOSIS.md) for full diagnostic reference.
