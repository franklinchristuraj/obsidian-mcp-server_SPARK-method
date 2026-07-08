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
        "OBSIDIAN_VAULT_PATH",
    ]

    for var in required_vars:
        value = os.getenv(var)
        if value:
            masked = value[:8] + "..." if "KEY" in var and len(value) > 8 else value
            print(f"  • {var}: {masked}")
        else:
            print(f"  ✗ {var}: MISSING")
            sys.exit(1)

    # Test vault access (filesystem-native - no REST API/plugin dependency)
    print("\n✓ Testing Vault Access:")
    client = ObsidianClient()

    if await client.health_check():
        print("  • Vault path: Readable")
        info = await client.get_vault_info()
        print(f"  • Vault Name: {info.get('name', 'Unknown')}")
    else:
        print("  ✗ Cannot read OBSIDIAN_VAULT_PATH")
        print("  Check that the path exists and is readable")
        sys.exit(1)

    print("\n✅ Setup verification complete!")
    print("🚀 Ready to start development!")


if __name__ == "__main__":
    asyncio.run(verify_setup())
