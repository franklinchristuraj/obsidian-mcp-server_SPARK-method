# Claude Desktop Setup with Stdio Bridge

## 🎯 Solution: Stdio Bridge for Claude Desktop

Claude Desktop expects **stdio transport** (not HTTP), so we've created a bridge that converts between stdio and your HTTP MCP server.

## 📁 Step 1: Download the Stdio Bridge

Download `mcp_stdio_bridge.py` to your local machine where Claude Desktop is installed.

**Download the file from**: `/root/obsidian-mcp-server/mcp_stdio_bridge.py`

Save it to a location like:
- **macOS**: `~/mcp_stdio_bridge.py`
- **Windows**: `C:\Users\YourName\mcp_stdio_bridge.py`

## 🔧 Step 2: Claude Desktop Configuration

Edit your Claude Desktop configuration file:

### **Configuration File Location:**
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

### **Add This Configuration:**

```json
{
  "mcpServers": {
    "obsidian-ziksaka": {
      "command": "python3",
      "args": ["/Users/YourUsername/mcp_stdio_bridge.py"]
    }
  }
}
```

**Important**: Replace `/Users/YourUsername/mcp_stdio_bridge.py` with the actual path where you saved the file.

### **Windows Example:**
```json
{
  "mcpServers": {
    "obsidian-ziksaka": {
      "command": "python",
      "args": ["C:\\Users\\YourName\\mcp_stdio_bridge.py"]
    }
  }
}
```

## 🔄 Step 3: Restart Claude Desktop

1. **Completely close** Claude Desktop
2. **Restart** the application
3. Look for the MCP server indicator

## ✅ Step 4: Verification

After restart, you should see:
1. **11 tools available** in Claude Desktop
2. **Server name**: "obsidian-ziksaka" 
3. **No connection errors** in Claude Desktop

## 🔍 Troubleshooting

### Issue: Python not found
**Error**: `python3: command not found`

**Solution**: 
- **macOS**: Install Python 3 via Homebrew: `brew install python3`
- **Windows**: Install Python from python.org and use `python` instead of `python3`

### Issue: Permission denied
**Solution**: Make the file executable:
```bash
chmod +x ~/mcp_stdio_bridge.py
```

### Issue: Module not found (httpx)
**Solution**: Install httpx:
```bash
pip3 install httpx
# or
pip install httpx
```

### Issue: Connection refused
**Check**: Verify your server is running:
```bash
curl -X POST https://mcp.ziksaka.com/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MCP_API_KEY" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}'
```

## 🧪 Manual Test

You can test the bridge manually:
```bash
echo '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}' | python3 mcp_stdio_bridge.py
```

Should return JSON with capabilities and 11 tools.

## 📋 What the Bridge Does

```
Claude Desktop ←→ stdio ←→ mcp_stdio_bridge.py ←→ HTTPS ←→ Your MCP Server
```

1. **Claude Desktop** sends JSON-RPC via stdin
2. **Bridge** forwards HTTP request to your server
3. **Your server** processes and responds
4. **Bridge** sends response back via stdout
5. **Claude Desktop** receives the response

## 🎉 Expected Result

Once configured correctly, you'll have access to all 11 Obsidian tools:
- ping, search_notes, read_note, create_note
- update_note, append_note, delete_note, list_notes  
- get_vault_structure, execute_command, keyword_search

Your remote MCP server will work seamlessly with Claude Desktop!
