#!/usr/bin/env python3
"""
Vault + MCP Server Diagnostic Script (filesystem-native architecture)

Replaces the old REST API / port-scanning diagnostic - there's no Obsidian
plugin or port to check anymore, just: is the vault path readable, and is
the MCP server listening.
"""
import os
import socket
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv()


def check_port_listening(port: int) -> bool:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("127.0.0.1", port))
        sock.close()
        return result == 0
    except Exception:
        return False


def run_command(cmd: str):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except Exception:
        return "", "Command failed", 1


def main():
    print("🔍 Obsidian MCP Server Diagnostic Report")
    print("=" * 50)

    vault_path = os.getenv("OBSIDIAN_VAULT_PATH", "")
    print("\n📁 Vault Path Check:")
    if not vault_path:
        print("❌ OBSIDIAN_VAULT_PATH not set")
    elif not os.path.isdir(vault_path):
        print(f"❌ Vault path does not exist: {vault_path}")
    else:
        print(f"✅ Vault path readable: {vault_path}")
        for scope in ("personal", "passion", "work", "parallax"):
            scope_dir = Path(vault_path) / scope
            count = len(list(scope_dir.rglob("*.md"))) if scope_dir.is_dir() else 0
            status = "✅" if scope_dir.is_dir() else "❌"
            print(f"   {status} {scope}/: {count} notes")

    mcp_port = int(os.getenv("MCP_PORT", "8888"))
    print(f"\n📡 MCP Server Port Check ({mcp_port}):")
    if check_port_listening(mcp_port):
        print(f"✅ Port {mcp_port} is accepting connections")
    else:
        print(f"❌ Port {mcp_port} is NOT listening")

    print("\n🔍 obsidian-mcp systemd service:")
    stdout, _, _ = run_command(
        "systemctl --user is-active obsidian-mcp.service 2>/dev/null"
    )
    print(f"   status: {stdout or 'unknown'}")

    print("\n" + "=" * 50)
    print("📋 DIAGNOSIS SUMMARY:")
    if vault_path and os.path.isdir(vault_path) and check_port_listening(mcp_port):
        print("✅ Vault is readable and MCP server is listening")
    else:
        print("❌ Something's misconfigured - check the sections above")
        print("🔧 Next steps:")
        print("   1. Verify OBSIDIAN_VAULT_PATH in .env")
        print("   2. Check: systemctl --user status obsidian-mcp.service")
        print("   3. Check logs: journalctl --user -u obsidian-mcp.service -n 50")


if __name__ == "__main__":
    main()
