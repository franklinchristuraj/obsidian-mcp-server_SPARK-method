#!/bin/bash
echo "📊 Obsidian MCP Server Status:"
echo "================================"
sudo systemctl status obsidian-mcp
echo ""
echo "🔗 Testing connectivity:"
curl -s -H "Authorization: Bearer $(grep MCP_API_KEY .env.production | cut -d'=' -f2)" \
     -H "Content-Type: application/json" \
     -X POST http://127.0.0.1:8888/mcp \
     -d '{"jsonrpc":"2.0","method":"ping","id":1}' | python3 -m json.tool
