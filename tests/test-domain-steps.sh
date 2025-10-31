#!/bin/bash
echo "🔍 Diagnostic Steps for mcp.ziksaka.com"
echo "====================================="

echo ""
echo "1. Testing DNS resolution:"
nslookup mcp.ziksaka.com

echo ""
echo "2. Testing local MCP server:"
curl -s -o /dev/null -w "Local MCP: %{http_code}\n" \
     -H "Authorization: Bearer ${MCP_API_KEY:-your-api-key}" \
     -H "Content-Type: application/json" \
     -X POST http://127.0.0.1:8888/mcp \
     -d '{"jsonrpc":"2.0","method":"ping","id":1}'

echo ""
echo "3. Testing domain HTTP (after proxy setup):"
timeout 10 curl -s -o /dev/null -w "HTTP: %{http_code}\n" \
     -H "Authorization: Bearer ${MCP_API_KEY:-your-api-key}" \
     -H "Content-Type: application/json" \
     -X POST http://mcp.ziksaka.com/mcp \
     -d '{"jsonrpc":"2.0","method":"ping","id":1}' || echo "HTTP: FAILED"

echo ""
echo "4. Testing domain HTTPS (after SSL setup):"
timeout 10 curl -s -o /dev/null -w "HTTPS: %{http_code}\n" \
     -H "Authorization: Bearer ${MCP_API_KEY:-your-api-key}" \
     -H "Content-Type: application/json" \
     -X POST https://mcp.ziksaka.com/mcp \
     -d '{"jsonrpc":"2.0","method":"ping","id":1}' || echo "HTTPS: FAILED"

echo ""
echo "🎯 Expected Results:"
echo "  - DNS: Should show your server IP (148.230.124.28)"
echo "  - Local MCP: Should show 200"
echo "  - HTTP: Should show 200 (after proxy setup)"
echo "  - HTTPS: Should show 200 (after SSL setup)"
