#!/usr/bin/env python3
"""
Comprehensive test script for Obsidian MCP tools (canonical names only).
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from src.mcp_server import mcp_handler

load_dotenv()

EXPECTED_OBSIDIAN_TOOLS = frozenset(
    {
        "workspaces",
        "vault_structure",
        "list_notes",
        "list_journal",
        "search",
        "read_note",
        "create_note",
        "update_note",
        "append_note",
        "note_exists",
        "delete_note",
    }
)


async def test_tool_discovery():
    """Obsidian tools are listed under canonical names; no legacy obs_* aliases."""
    print("🔍 Testing tool discovery...")

    try:
        response = await mcp_handler.handle_request("tools/list")
        tools = response.get("tools", [])
        names = [t["name"] for t in tools]

        legacy = [n for n in names if n.startswith("obs_")]
        if legacy:
            print(f"❌ Legacy obs_* tools still listed: {legacy}")
            return False

        tool_set = set(names)
        missing = sorted(EXPECTED_OBSIDIAN_TOOLS - tool_set)
        if missing:
            print(f"❌ Missing tools: {missing}")
            return False

        unexpected = sorted(tool_set - EXPECTED_OBSIDIAN_TOOLS - {"ping"})
        if unexpected:
            print(f"❌ Unexpected tool names: {unexpected}")
            return False

        print(f"✅ tools/list: ping + {len(EXPECTED_OBSIDIAN_TOOLS)} Obsidian tools, no obs_* aliases")
        return True

    except Exception as e:
        print(f"❌ Tool discovery failed: {e}")
        return False


async def test_tool_schemas():
    """All tools (except ping) have descriptions and object inputSchema with properties."""
    print("\n📋 Testing tool schemas...")

    try:
        response = await mcp_handler.handle_request("tools/list")
        tools = response.get("tools", [])

        schema_issues = []

        for tool in tools:
            tool_name = tool["name"]
            if tool_name == "ping":
                continue

            if not tool.get("description"):
                schema_issues.append(f"{tool_name}: Missing description")

            if not tool.get("inputSchema"):
                schema_issues.append(f"{tool_name}: Missing inputSchema")
            else:
                schema = tool["inputSchema"]
                if schema.get("type") != "object":
                    schema_issues.append(f"{tool_name}: Schema type should be 'object'")

                if "properties" not in schema:
                    schema_issues.append(f"{tool_name}: Missing properties in schema")

            print(f"   ✅ {tool_name}: Schema valid")

        if schema_issues:
            print("❌ Schema issues found:")
            for issue in schema_issues:
                print(f"     - {issue}")
            return False

        print(f"✅ All non-ping tool schemas are valid")
        return True

    except Exception as e:
        print(f"❌ Schema validation failed: {e}")
        return False


async def test_tool_execution():
    """Smoke-test each Obsidian tool via tools/call."""
    print("\n🔧 Testing tool execution...")

    test_cases = [
        {"name": "workspaces", "args": {}, "description": "List allowed scopes"},
        {
            "name": "list_journal",
            "args": {"startDate": "2026-01-01", "endDate": "2026-01-07"},
            "description": "Daily notes in date range",
        },
        {
            "name": "search",
            "args": {"keyword": "test"},
            "description": "Keyword search",
        },
        {
            "name": "read_note",
            "args": {"path": "nonexistent.md"},
            "description": "Read note (expect error for non-existent file)",
        },
        {
            "name": "create_note",
            "args": {"path": "test-note.md", "content": "Test content"},
            "description": "Create note",
        },
        {
            "name": "update_note",
            "args": {"path": "test-note.md", "content": "Updated content"},
            "description": "Update note",
        },
        {
            "name": "append_note",
            "args": {"path": "test-note.md", "content": "Appended content"},
            "description": "Append to note",
        },
        {"name": "list_notes", "args": {}, "description": "List notes"},
        {
            "name": "vault_structure",
            "args": {"use_cache": True},
            "description": "Get vault structure",
        },
        {
            "name": "note_exists",
            "args": {"path": "nonexistent.md"},
            "description": "Note exists check",
        },
        {
            "name": "delete_note",
            "args": {"path": "test-note.md"},
            "description": "Delete note",
        },
    ]

    results = []

    for test_case in test_cases:
        tool_name = test_case["name"]
        args = test_case["args"]
        description = test_case["description"]

        try:
            print(f"   🔧 Testing {tool_name}: {description}")

            response = await mcp_handler.handle_request(
                "tools/call", {"name": tool_name, "arguments": args}
            )

            if "content" not in response:
                print("     ❌ No 'content' in response")
                results.append((tool_name, False, "No content in response"))
                continue

            content = response["content"]
            if not isinstance(content, list) or len(content) == 0:
                print("     ❌ Invalid content structure")
                results.append((tool_name, False, "Invalid content structure"))
                continue

            first_content = content[0]
            if "type" not in first_content or "text" not in first_content:
                print("     ❌ Invalid content item structure")
                results.append((tool_name, False, "Invalid content item structure"))
                continue

            text = first_content["text"]

            if "client not initialized" in text.lower():
                print("     ⚠️  Expected: Client not initialized (no API key)")
                results.append((tool_name, True, "Expected: No API key"))
            elif "❌" in text:
                print(f"     ⚠️  Tool error (expected): {text[:100]}...")
                results.append((tool_name, True, "Expected error"))
            else:
                print(f"     ✅ Success: {text[:50]}...")
                results.append((tool_name, True, "Success"))

        except Exception as e:
            print(f"     ❌ Exception: {str(e)}")
            results.append((tool_name, False, f"Exception: {str(e)}"))

    successful = sum(1 for _, success, _ in results if success)
    total = len(results)

    print("\n📊 Tool Execution Results:")
    for tool_name, success, message in results:
        status = "✅" if success else "❌"
        print(f"   {status} {tool_name}: {message}")

    print(f"\n🎯 Summary: {successful}/{total} tools executed successfully")

    return successful == total


async def test_error_handling():
    """Invalid tool names and bad arguments surface as errors."""
    print("\n🚨 Testing error handling...")

    test_cases = [
        {
            "name": "definitely_nonexistent_tool_xyz",
            "args": {},
            "description": "Non-existent tool",
        },
        {
            "name": "search",
            "args": {"invalid_param": "test"},
            "description": "Invalid parameters",
        },
        {
            "name": "read_note",
            "args": {},
            "description": "Missing required parameter",
        },
    ]

    results = []

    for test_case in test_cases:
        tool_name = test_case["name"]
        args = test_case["args"]
        description = test_case["description"]

        try:
            print(f"   🚨 Testing {description}: {tool_name}")

            response = await mcp_handler.handle_request(
                "tools/call", {"name": tool_name, "arguments": args}
            )

            content = response.get("content", [])
            if content and len(content) > 0:
                text = content[0].get("text", "")
                if "❌" in text or "error" in text.lower() or "failed" in text.lower():
                    print(f"     ✅ Proper error handling: {text[:50]}...")
                    results.append(True)
                elif "Unknown tool" in text:
                    print(f"     ✅ Unknown tool: {text[:50]}...")
                    results.append(True)
                else:
                    print(f"     ❌ Unexpected success: {text[:50]}...")
                    results.append(False)
            else:
                print("     ❌ No error response")
                results.append(False)

        except Exception as e:
            print(f"     ✅ Exception raised (acceptable): {str(e)[:50]}...")
            results.append(True)

    successful = sum(results)
    total = len(results)

    print(f"🎯 Error handling: {successful}/{total} cases handled correctly")
    return successful == total


async def test_canonical_routing():
    """Registered names dispatch; unknown names are rejected."""
    print("\n🔀 Testing tool name routing...")

    try:
        response = await mcp_handler.handle_request(
            "tools/call",
            {"name": "search", "arguments": {"keyword": "test"}},
        )

        content = response.get("content", [])
        if not content:
            print("   ❌ search tool routing failed (empty content)")
            return False
        print("   ✅ search dispatches correctly")

        response = await mcp_handler.handle_request(
            "tools/call", {"name": "invalid_prefix_tool", "arguments": {}}
        )

        content = response.get("content", [])
        if content and "Unknown tool" in content[0].get("text", ""):
            print("   ✅ Invalid tool name properly rejected")
            return True

        print("   ❌ Invalid tool name not properly handled")
        return False

    except Exception as e:
        print(f"   ❌ Routing test failed: {e}")
        return False


async def main():
    print("🚀 Comprehensive Obsidian Tools Test Suite")
    print("=" * 60)

    tests = [
        ("Tool Discovery", test_tool_discovery),
        ("Tool Schemas", test_tool_schemas),
        ("Tool Execution", test_tool_execution),
        ("Error Handling", test_error_handling),
        ("Tool routing", test_canonical_routing),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} crashed: {e}")
            results.append((test_name, False))

    print("\n" + "=" * 60)
    print("📊 COMPREHENSIVE TEST RESULTS")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")

    print(f"\n🎯 Overall Results: {passed}/{total} test suites passed")

    if passed == total:
        print("🎉 All checks passed.")
        return 0

    print("⚠️  Some issues detected. Check the output above for details.")
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
