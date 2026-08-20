# MCP Endpoint Implementation

## Overview

The MCP endpoint at `POST /mcp` implements Streamable HTTP with **dual-compat**:

| Era | How clients connect |
|-----|---------------------|
| Legacy (≤ `2025-11-25`) | `initialize` handshake; optional `Mcp-Session-Id` echo |
| Modern (`2026-07-28`) | Stateless; `server/discover` optional; every request carries `_meta` + `Mcp-Method` / `Mcp-Name` headers |

No sticky sessions are required. `Mcp-Session-Id` is correlation-only for observability.

## Features

- JSON-RPC 2.0 with error codes including `-32020` (header mismatch)
- Bearer / OAuth authentication via `src/auth.py`
- `server/discover`, `initialize`, tools / resources / prompts
- SEP-2549 cache hints (`ttlMs`, `cacheScope`) on list/read
- Tasks extension (`tasks/get`, `tasks/update`) for heavy vault tools
- MCP Apps (`io.modelcontextprotocol/ui`)
- Legacy `GET /mcp` keepalive (compatibility only; modern clients should not depend on it)

## API Usage

### Endpoint
```
POST /mcp
Content-Type: application/json
Authorization: Bearer <your-api-key>
```

### Modern request (2026-07-28)
```
POST /mcp
Mcp-Protocol-Version: 2026-07-28
Mcp-Method: tools/call
Mcp-Name: ping
Authorization: Bearer <key>
Content-Type: application/json

{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "ping",
    "arguments": {},
    "_meta": {
      "io.modelcontextprotocol/protocolVersion": "2026-07-28",
      "io.modelcontextprotocol/clientInfo": {"name": "my-client", "version": "1.0"},
      "io.modelcontextprotocol/clientCapabilities": {
        "extensions": {"io.modelcontextprotocol/tasks": {}}
      }
    }
  }
}
```

Header values must match the JSON-RPC body or the server returns `-32020`.

### Legacy initialize
```json
{
  "jsonrpc": "2.0",
  "method": "initialize",
  "params": {
    "protocolVersion": "2025-06-18",
    "capabilities": {},
    "clientInfo": {"name": "test-client", "version": "1.0.0"}
  },
  "id": 2
}
```

### `server/discover`
Stateless capability probe (no session). Returns `protocolVersion`, `capabilities` (including UI + Tasks extensions), `serverInfo`, and `instructions`.

### Cache hints
`tools/list`, `prompts/list`, and `resources/list` include:
- `ttlMs` — freshness hint in milliseconds
- `cacheScope`: `"private"`

### Tasks (heavy tools)
When the client advertises `extensions["io.modelcontextprotocol/tasks"]`, these tools return a task handle immediately:

- `lint_vault`, `build_context`, `impact_rollup`, `graph_health`, `get_dossier`

Poll with `tasks/get` `{ "taskId": "..." }`. Cancel via `tasks/update` with `status: "cancelled"`.
Without Tasks capability, those tools still run synchronously (legacy behavior).

## Error Responses

| Code | Meaning |
|------|---------|
| -32700 | Parse error |
| -32600 | Invalid Request |
| -32601 | Method not found |
| -32602 | Invalid params |
| -32603 | Internal error |
| -32020 | Header mismatch (`Mcp-Method` / `Mcp-Name`) |

## Authentication

Requires a valid Bearer token (workspace key, static `MCP_API_KEY`, or OAuth access token).
