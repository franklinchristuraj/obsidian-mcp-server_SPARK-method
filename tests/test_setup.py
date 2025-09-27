#!/usr/bin/env python
"""Quick setup verification script"""
import asyncio
import os
import sys
from dotenv import load_dotenv
from src.clients.obsidian_client import ObsidianClient


async def verify_setup():
    load_dotenv()

    print("🔍 Verifying Obsidian MCP Server Setup...\n")

    # Check environment variables
    print("✓ Environment Variables:")
    required_vars = [
        "MCP_HOST",
        "MCP_PORT",
        "MCP_API_KEY",
        "OBSIDIAN_API_URL",
        "OBSIDIAN_API_KEY",
    ]

    for var in required_vars:
        value = os.getenv(var)
        if value:
            masked = value[:8] + "..." if len(value) > 8 else "***"
            print(f"  • {var}: {masked}")
        else:
            print(f"  ✗ {var}: MISSING")
            sys.exit(1)

    # Test Obsidian connection
    print("\n✓ Testing Obsidian Connection:")
    client = ObsidianClient()

    if await client.health_check():
        print("  • Obsidian REST API: Connected")
        info = await client.get_vault_info()
        print(f"  • Vault Name: {info.get('name', 'Unknown')}")
    else:
        print("  ✗ Cannot connect to Obsidian REST API")
        print("  Make sure Obsidian is running with Local REST API plugin enabled")
        sys.exit(1)

    print("\n✅ Setup verification complete!")
    print("🚀 Ready to start development!")


if __name__ == "__main__":
    asyncio.run(verify_setup())
