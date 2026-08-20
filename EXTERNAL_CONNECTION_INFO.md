# External Connection Information

## 🌐 Public Endpoints

### MCP Server Endpoint
```
https://mcp.ziksaka.com/mcp
```

### Health Check Endpoint (No auth required)
```
https://mcp.ziksaka.com/health
```

## 🔑 API Key

Your API key is stored in `.env` file:
```bash
MCP_API_KEY=your-mcp-api-key
```

**⚠️ Security Note:** Keep this API key secure. Do not share it publicly or commit it to version control.

## 🔒 Authentication

All MCP requests require Bearer token authentication:

```bash
Authorization: Bearer YOUR_API_KEY
```

### 🔌 Claude.ai Connector Configuration

When connecting via Claude.ai's connector interface, use these settings:

**Connector Fields:**
- **Remote URL**: `https://mcp.ziksaka.com/mcp`
- **OAuth Client ID**: `franklinchris`
- **OAuth Client Secret**: your API key from `.env`

**How it works:**
The server accepts authentication via multiple methods:
1. **Bearer token** in `Authorization` header (standard method)
2. **OAuth-style**: `client_id` + `client_secret` query parameters or headers (for Claude.ai connectors)
3. **Direct API key**: `api_key` query parameter or `X-API-Key` header (backward compatibility)

The server validates that the **OAuth Client Secret** matches your `MCP_API_KEY` from `.env`. The **OAuth Client ID** should be set to `franklinchris`.

## 📝 Example Usage

### Health Check (No Auth)
```bash
curl https://mcp.ziksaka.com/health
```

### MCP Request (With Auth)
```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
     -H "Content-Type: application/json" \
     -X POST https://mcp.ziksaka.com/mcp \
     -d '{
       "jsonrpc": "2.0",
       "method": "ping",
       "id": 1
     }'
```

### List Available Tools
```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
     -H "Content-Type: application/json" \
     -X POST https://mcp.ziksaka.com/mcp \
     -d '{
       "jsonrpc": "2.0",
       "method": "tools/list",
       "id": 1
     }'
```

### Call a Tool
```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
     -H "Content-Type: application/json" \
     -X POST https://mcp.ziksaka.com/mcp \
     -d '{
       "jsonrpc": "2.0",
       "method": "tools/call",
       "params": {
         "name": "obs_list_notes",
         "arguments": {
           "folder": "02_projects"
         }
       },
       "id": 1
     }'
```

## 🛠️ Available Tools (11 Total)

1. `ping` - Test connectivity
2. `obs_search_notes` - Search notes
3. `obs_read_note` - Read note content
4. `obs_create_note` - Create new note
5. `obs_update_note` - Update note
6. `obs_append_note` - Append to note
7. `obs_delete_note` - Delete note
8. `obs_list_notes` - List notes
9. `obs_get_vault_structure` - Get vault structure
10. `obs_execute_command` - Execute Obsidian command
11. `obs_keyword_search` - Keyword search

## 🔐 Security

- ✅ HTTPS encryption enabled (Let's Encrypt SSL)
- ✅ API key authentication required
- ✅ Server behind Nginx Proxy Manager
- ✅ Rate limiting available
- ✅ CORS configured

## 📚 Documentation

See `docs/` directory for:
- API reference: `docs/MCP_ENDPOINT.md`
- Setup guides: `docs/setup/`
- Deployment: `docs/deployment/`

