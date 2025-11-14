#!/bin/bash
API_KEY=$(grep MCP_API_KEY /home/franklinchris/obsidian-mcp-server/.env | cut -d'=' -f2)

echo "Testing external access to mcp.ziksaka.com..."
echo ""

echo "1. Health check:"
curl -s https://mcp.ziksaka.com/health | python3 -m json.tool
echo ""

echo "2. MCP ping:"
curl -s -H "Authorization: Bearer $API_KEY" \
     -H "Content-Type: application/json" \
     -X POST https://mcp.ziksaka.com/mcp \
     -d '{"jsonrpc":"2.0","method":"ping","id":1}' | python3 -m json.tool
