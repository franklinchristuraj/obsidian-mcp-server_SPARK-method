#!/bin/bash
# Obsidian MCP Service Management Script

case "$1" in
    start)
        echo "🚀 Starting Obsidian MCP service..."
        systemctl --user start obsidian-mcp.service
        sleep 2
        systemctl --user status obsidian-mcp.service --no-pager | head -10
        ;;
    stop)
        echo "🛑 Stopping Obsidian MCP service..."
        systemctl --user stop obsidian-mcp.service
        ;;
    restart)
        echo "🔄 Restarting Obsidian MCP service..."
        systemctl --user restart obsidian-mcp.service
        sleep 2
        systemctl --user status obsidian-mcp.service --no-pager | head -10
        ;;
    status)
        systemctl --user status obsidian-mcp.service --no-pager
        ;;
    logs)
        echo "📜 Obsidian MCP service logs (last 50 lines):"
        echo "============================================="
        journalctl --user -u obsidian-mcp.service -n 50 --no-pager
        echo ""
        echo "📡 Live log streaming (Ctrl+C to exit):"
        journalctl --user -u obsidian-mcp.service -f
        ;;
    enable)
        echo "✅ Enabling Obsidian MCP service..."
        systemctl --user enable obsidian-mcp.service
        loginctl enable-linger $USER
        echo "Service enabled and will start on boot"
        ;;
    disable)
        echo "❌ Disabling Obsidian MCP service..."
        systemctl --user disable obsidian-mcp.service
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs|enable|disable}"
        echo ""
        echo "Commands:"
        echo "  start    - Start the service"
        echo "  stop     - Stop the service"
        echo "  restart  - Restart the service"
        echo "  status   - Show service status"
        echo "  logs     - Show service logs"
        echo "  enable   - Enable service to start on boot"
        echo "  disable  - Disable service from starting on boot"
        exit 1
        ;;
esac

exit 0

