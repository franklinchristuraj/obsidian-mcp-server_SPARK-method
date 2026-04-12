# Claude Desktop Remote Connector Setup

> **Note:** This document may list older tool counts and names. For current MCP tools, scopes, and paths, use the **`vault_mcp_agent_guide`** prompt on the server and project handover docs.

## 🎯 Direct Connection to Remote MCP Server

Your MCP server is working perfectly with **11 tools available**. Here's how to connect Claude Desktop using remote connectors.

## ✅ Server Status Verified
- **Remote Endpoint**: ✅ Working at https://mcp.ziksaka.com/mcp
- **Tools**: ✅ 11 tools properly exposed  
- **Authentication**: ✅ Configured and working with proxy
- **Status**: ✅ Active and ready for Claude Desktop

## 🔧 Claude Desktop Remote Connector Setup

Since Claude Desktop only shows these fields for custom connectors:
- **Name**
- **Remote MCP Server URL** 
- **OAuth Client ID** (optional)
- **OAuth Client Secret** (optional)

### Configuration Steps:

1. **Open Claude Desktop**
2. **Go to Settings** → **Connectors**  
3. **Click "Add custom connector"**
4. **Fill in the details**:
   - **Name**: `Obsidian Ziksaka MCP`
   - **Remote MCP Server URL**: `https://mcp.ziksaka.com/mcp`
   - **OAuth Client ID**: *(leave empty)*
   - **OAuth Client Secret**: *(leave empty)*

### Important: Nginx Proxy Manager Configuration

Since you're handling authentication in Nginx Proxy Manager, you need to ensure:

1. **Proxy is forwarding to**: `http://127.0.0.1:8888/mcp`
2. **Authentication header**: Add `Authorization: Bearer internal-server-key`
3. **CORS headers**: Allow Claude Desktop's requests

#### Required Nginx Headers:
```
Authorization: Bearer internal-server-key
Content-Type: application/json
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: POST, OPTIONS
Access-Control-Allow-Headers: Content-Type, Authorization
```

## 🎉 Nginx Configuration Working!

**Status**: ✅ Proxy working correctly

### ⚠️ Add CORS Headers for Claude Desktop

Your current Nginx config works but needs CORS headers for Claude Desktop. Update your advanced configuration to include:

```nginx
# Handle CORS preflight requests
if ($request_method = 'OPTIONS') {
    add_header 'Access-Control-Allow-Origin' '*' always;
    add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS' always;
    add_header 'Access-Control-Allow-Headers' 'Content-Type, Authorization' always;
    add_header 'Access-Control-Max-Age' 1728000 always;
    add_header 'Content-Type' 'text/plain charset=UTF-8' always;
    add_header 'Content-Length' 0 always;
    return 204;
}

# CORS headers for actual requests  
add_header 'Access-Control-Allow-Origin' '*' always;
add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS' always;
add_header 'Access-Control-Allow-Headers' 'Content-Type, Authorization' always;
```

**Complete config**: See `nginx_mcp_config.conf` for the full configuration.

### ✅ Verification:
```bash
curl -X POST https://mcp.ziksaka.com/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}'
```

Returns 11 tools successfully! 🎉

## 🧪 Testing the Connection

After setup, you should see:
1. **Connector indicator** in Claude Desktop interface
2. **11 tools available**:
   - ping
   - search_notes  
   - read_note
   - create_note
   - update_note
   - append_note
   - delete_note
   - list_notes
   - get_vault_structure
   - execute_command
   - keyword_search

## 🔍 Troubleshooting

### Tools Not Showing Up
1. **Check Claude Desktop logs**:
   - macOS: `~/Library/Logs/Claude/mcp.log`
   - Windows: `%APPDATA%\Claude\logs\mcp.log`

2. **Verify server response**:
```bash
curl -X POST https://mcp.ziksaka.com/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-api-key" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}'
```

### Authentication Issues
- Ensure your API key is correct
- Check that the Authorization header format matches what your server expects

### Connection Refused
- Verify the server is running: `systemctl status obsidian-mcp.service`
- Check server logs: `journalctl -u obsidian-mcp.service -f`

## 📋 Current Server Configuration

Your server is properly configured with:
- ✅ **11 MCP tools** properly exposed
- ✅ **JSON-RPC 2.0** protocol compliance  
- ✅ **Bearer token authentication**
- ✅ **HTTPS endpoint** at mcp.ziksaka.com
- ✅ **Proper capabilities** returned in initialize

## 🚀 Next Steps

1. Try the UI method first (Method 1)
2. If that doesn't work, use the config file method (Method 2)  
3. Check logs for any authentication or connection issues
4. Verify the API key is working with the curl command above

The server-side fix has been applied and your MCP server is working correctly. The issue was the outdated handler that returned empty capabilities - this has been resolved and the production server restarted.
