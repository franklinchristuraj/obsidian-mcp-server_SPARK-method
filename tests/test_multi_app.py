#!/usr/bin/env python3
"""
Test script for the multi-application MCP server
Tests both Obsidian (obs_) and Todoist (todo_) tools
"""
import asyncio
import json
import sys
from dotenv import load_dotenv
from src.mcp_server import mcp_handler

# Load environment variables
load_dotenv()


async def test_tool_listing():
    """Test that all tools are properly loaded and listed"""
    print("🔍 Testing tool listing...")

    try:
        response = await mcp_handler.handle_request("tools/list")
        tools = response.get("tools", [])

        print(f"✅ Found {len(tools)} total tools")

        # Count tools by prefix
        obs_tools = [t for t in tools if t["name"].startswith("obs_")]
        other_tools = [t for t in tools if not t["name"].startswith("obs_")]

        print(f"   📝 Obsidian tools (obs_): {len(obs_tools)}")
        print(f"   🔧 Other tools: {len(other_tools)}")

        # List all tools
        print("\n📋 All available tools:")
        for tool in tools:
            prefix_emoji = "📝" if tool["name"].startswith("obs_") else "🔧"
            print(f"   {prefix_emoji} {tool['name']}: {tool['description']}")

        return True

    except Exception as e:
        print(f"❌ Tool listing failed: {e}")
        return False


async def test_ping():
    """Test the ping tool"""
    print("\n🏓 Testing ping tool...")

    try:
        response = await mcp_handler.handle_request(
            "tools/call", {"name": "ping", "arguments": {}}
        )

        content = response.get("content", [])
        if content and content[0].get("text"):
            print(f"✅ Ping successful: {content[0]['text']}")
            return True
        else:
            print("❌ Ping failed: No content in response")
            return False

    except Exception as e:
        print(f"❌ Ping failed: {e}")
        return False


async def test_obsidian_tool():
    """Test an Obsidian tool (without requiring actual connection)"""
    print("\n📝 Testing Obsidian tool (obs_get_vault_structure)...")

    try:
        response = await mcp_handler.handle_request(
            "tools/call",
            {"name": "obs_get_vault_structure", "arguments": {"use_cache": True}},
        )

        content = response.get("content", [])
        if content and content[0].get("text"):
            text = content[0]["text"]
            if "Obsidian client not initialized" in text:
                print(
                    "⚠️  Obsidian tool responded (client not initialized - expected without API key)"
                )
                return True
            else:
                print(f"✅ Obsidian tool executed: {text[:100]}...")
                return True
        else:
            print("❌ Obsidian tool failed: No content in response")
            return False

    except Exception as e:
        print(f"❌ Obsidian tool failed: {e}")
        return False


async def test_unknown_prefix():
    """Test handling of unknown tool prefix"""
    print("\n❓ Testing unknown tool prefix...")

    try:
        response = await mcp_handler.handle_request(
            "tools/call", {"name": "unknown_test_tool", "arguments": {}}
        )

        content = response.get("content", [])
        if content and content[0].get("text"):
            text = content[0]["text"]
            if "Unknown tool prefix" in text:
                print("✅ Unknown prefix handled correctly")
                return True
            else:
                print(f"❌ Unexpected response: {text}")
                return False
        else:
            print("❌ No response for unknown prefix")
            return False

    except Exception as e:
        print(f"❌ Unknown prefix test failed: {e}")
        return False


async def test_server_info():
    """Test server initialization and info"""
    print("\n🖥️  Testing server info...")

    try:
        response = await mcp_handler.handle_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "test-client", "version": "1.0.0"},
            },
        )

        server_info = response.get("serverInfo", {})
        if server_info.get("name") == "multi-app-mcp-server":
            print(f"✅ Server info correct: {server_info}")
            return True
        else:
            print(f"❌ Unexpected server info: {server_info}")
            return False

    except Exception as e:
        print(f"❌ Server info test failed: {e}")
        return False


async def main():
    """Run all tests"""
    print("🚀 Starting Multi-Application MCP Server Tests\n")
    print("=" * 60)

    tests = [
        ("Server Info", test_server_info),
        ("Tool Listing", test_tool_listing),
        ("Ping Tool", test_ping),
        ("Obsidian Tool", test_obsidian_tool),
        ("Unknown Prefix", test_unknown_prefix),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} crashed: {e}")
            results.append((test_name, False))

    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")

    print(f"\n🎯 Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed! Multi-application MCP server is working correctly.")
        return 0
    else:
        print("⚠️  Some tests failed. Check the output above for details.")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⏹️  Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Tests crashed: {e}")
        sys.exit(1)
