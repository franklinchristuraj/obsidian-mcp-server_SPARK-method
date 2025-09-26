#!/usr/bin/env python3
"""
Install Claude Desktop MCP Bridge
Downloads and configures the stdio bridge for Claude Desktop
"""
import os
import json
import sys
import shutil
from pathlib import Path


def get_claude_config_path():
    """Get Claude Desktop config file path based on OS"""
    home = Path.home()

    if sys.platform == "darwin":  # macOS
        return (
            home
            / "Library"
            / "Application Support"
            / "Claude"
            / "claude_desktop_config.json"
        )
    elif sys.platform == "win32":  # Windows
        return home / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json"
    else:  # Linux
        return home / ".config" / "claude" / "claude_desktop_config.json"


def install_bridge():
    """Install the stdio bridge to user's home directory"""
    bridge_source = Path(__file__).parent / "mcp_stdio_bridge.py"
    bridge_dest = Path.home() / "mcp_stdio_bridge.py"

    if not bridge_source.exists():
        print("❌ mcp_stdio_bridge.py not found in current directory")
        return None

    try:
        shutil.copy2(bridge_source, bridge_dest)
        # Make executable on Unix systems
        if sys.platform != "win32":
            bridge_dest.chmod(0o755)
        print(f"✅ Installed bridge to: {bridge_dest}")
        return bridge_dest
    except Exception as e:
        print(f"❌ Failed to copy bridge: {e}")
        return None


def update_claude_config(bridge_path: Path):
    """Update Claude Desktop configuration"""
    config_path = get_claude_config_path()

    # Create config directory if it doesn't exist
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing config or create new
    if config_path.exists():
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
        except json.JSONDecodeError:
            config = {}
    else:
        config = {}

    # Ensure mcpServers section exists
    if "mcpServers" not in config:
        config["mcpServers"] = {}

    # Add our server
    python_cmd = "python" if sys.platform == "win32" else "python3"

    config["mcpServers"]["obsidian-ziksaka"] = {
        "command": python_cmd,
        "args": [str(bridge_path)],
    }

    # Write updated config
    try:
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        print(f"✅ Updated Claude Desktop config: {config_path}")
        return True
    except Exception as e:
        print(f"❌ Failed to update config: {e}")
        return False


def check_dependencies():
    """Check if required dependencies are installed"""
    try:
        import httpx

        print("✅ httpx dependency found")
        return True
    except ImportError:
        print("❌ httpx not found. Install with: pip install httpx")
        return False


def main():
    """Main installation flow"""
    print("🚀 Installing Claude Desktop MCP Bridge for Obsidian...")
    print()

    # Check dependencies
    if not check_dependencies():
        print("\nPlease install httpx first:")
        print("  pip install httpx")
        print("  # or")
        print("  pip3 install httpx")
        sys.exit(1)

    # Install bridge
    bridge_path = install_bridge()
    if not bridge_path:
        sys.exit(1)

    # Update config
    if not update_claude_config(bridge_path):
        sys.exit(1)

    print()
    print("🎉 Installation complete!")
    print()
    print("Next steps:")
    print("1. Restart Claude Desktop completely")
    print("2. Look for 'obsidian-ziksaka' in your MCP servers")
    print("3. You should see 11 tools available")
    print()
    print("If you have issues:")
    print("- Check Claude Desktop logs for error messages")
    print("- Ensure Python 3 and httpx are installed")
    print("- Verify the server is running at https://mcp.ziksaka.com/mcp")
    print()
    print(f"Bridge installed at: {bridge_path}")
    print(f"Config updated at: {get_claude_config_path()}")


if __name__ == "__main__":
    main()
