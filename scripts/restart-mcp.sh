#!/bin/bash
echo "🔄 Restarting Obsidian MCP Server..."
sudo systemctl restart obsidian-mcp
sleep 3
sudo systemctl status obsidian-mcp
echo "✅ Restart complete"
