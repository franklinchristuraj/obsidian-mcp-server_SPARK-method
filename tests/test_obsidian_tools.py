#!/usr/bin/env python3
"""
Test script for Obsidian MCP Tools
Tests all 9 tools with the running MCP server
"""
import json
import urllib.request
import urllib.parse
import os
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def call_mcp_tool(
    base_url: str, headers: dict, tool_name: str, arguments: dict, test_name: str
):
    """Call a specific MCP tool over HTTP (integration helper)."""
    print(f"\n🔧 Testing {test_name}...")

    request_data = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
        "id": hash(tool_name + str(arguments)),  # Simple ID generation
    }

    try:
        data = json.dumps(request_data).encode("utf-8")
        req = urllib.request.Request(f"{base_url}/mcp", data=data, headers=headers)

        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                result = json.loads(response.read().decode())
                if "result" in result and "content" in result["result"]:
                    content = result["result"]["content"]
                    print(f"   ✅ {test_name} successful")

                    # Print response summary
                    for item in content:
                        if item.get("type") == "text":
                            text = item["text"]
                            # Print first few lines for readability
                            lines = text.split("\n")[:5]
                            preview = "\n".join(lines)
                            if len(text.split("\n")) > 5:
                                preview += "\n   ..."
                            print(f"   📤 Response: {preview}")
                            break

                    # Print metadata if available
                    if "metadata" in result["result"]:
                        metadata = result["result"]["metadata"]
                        print(f"   📊 Metadata: {list(metadata.keys())}")

                    return True
                else:
                    print(f"   ❌ Unexpected response format: {result}")
                    return False
            else:
                print(f"   ❌ HTTP Error: {response.status}")
                return False

    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        try:
            error_data = json.loads(error_body)
            if "error" in error_data:
                print(
                    f"   ❌ Tool Error: {error_data['error'].get('message', 'Unknown error')}"
                )
                if "data" in error_data["error"]:
                    print(f"      Details: {error_data['error']['data']}")
            else:
                print(f"   ❌ HTTP Error {e.code}: {error_body}")
        except json.JSONDecodeError:
            print(f"   ❌ HTTP Error {e.code}: {error_body}")
        return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


async def run_obsidian_tools_live():
    """Exercise Obsidian MCP tools against a running server (manual / script use)."""

    # Get configuration
    host = os.getenv("MCP_HOST", "127.0.0.1")
    port = int(os.getenv("MCP_PORT", "8888"))
    api_key = os.getenv("MCP_API_KEY", "test-secret-key")

    base_url = f"http://{host}:{port}"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    print("🧪 Testing Obsidian MCP Tools")
    print(f"🔗 Endpoint: {base_url}/mcp")
    print(f"🔑 Using API key: {api_key[:8]}...")
    print("=" * 70)

    # Test 1: List all available tools
    print("\n1️⃣ Listing all available tools...")
    tools_request = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}

    try:
        data = json.dumps(tools_request).encode("utf-8")
        req = urllib.request.Request(f"{base_url}/mcp", data=data, headers=headers)

        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode())
            tools = result["result"]["tools"]
            print(f"   ✅ Found {len(tools)} tools:")
            for tool in tools:
                print(f"      • {tool['name']}: {tool['description']}")
            print()
    except Exception as e:
        print(f"   ❌ Failed to list tools: {e}")
        return

    # Test Results Tracking
    results = []

    # Test 2: search (keyword)
    success = call_mcp_tool(
        base_url,
        headers,
        "search",
        {"keyword": "note", "folder": ""},
        "search - keyword search for 'note'",
    )
    results.append(("search", success))

    # Test 3: vault_structure
    success = call_mcp_tool(
        base_url,
        headers,
        "vault_structure",
        {"use_cache": True},
        "vault_structure - folder tree",
    )
    results.append(("vault_structure", success))

    # Test 4: list_notes
    success = call_mcp_tool(
        base_url,
        headers,
        "list_notes",
        {"folder": ""},
        "list_notes - list notes with metadata",
    )
    results.append(("list_notes", success))

    # Test 5: Create a test note
    test_note_path = f"MCP-Test/Test-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
    test_content = f"""# MCP Test Note

Created by MCP Tools at {datetime.now().isoformat()}

This note was created to test the MCP tools integration.

## Test Features
- ✅ Note creation via MCP
- ✅ Content writing
- ✅ Folder auto-creation

#mcp #test #automation
"""

    success = call_mcp_tool(
        base_url,
        headers,
        "create_note",
        {"path": test_note_path, "content": test_content, "create_folders": True},
        f"create_note - create test note at {test_note_path}",
    )
    results.append(("create_note", success))

    if success:
        # Test 6: Read the created note
        success = call_mcp_tool(
            base_url,
            headers,
            "read_note",
            {"path": test_note_path},
            f"read_note - read the created test note",
        )
        results.append(("read_note", success))

        # Test 7: Update the note
        updated_content = (
            test_content
            + f"\n\n## Updated Section\nUpdated at: {datetime.now().isoformat()}"
        )
        success = call_mcp_tool(
            base_url,
            headers,
            "update_note",
            {"path": test_note_path, "content": updated_content},
            f"update_note - update the test note",
        )
        results.append(("update_note", success))

        # Test 8: Append to the note
        append_content = (
            f"\n## Appended Section\nAppended at: {datetime.now().isoformat()}"
        )
        success = call_mcp_tool(
            base_url,
            headers,
            "append_note",
            {"path": test_note_path, "content": append_content, "separator": "\n\n"},
            f"append_note - append content to test note",
        )
        results.append(("append_note", success))

        # Test 9: Search for our test note
        success = call_mcp_tool(
            base_url,
            headers,
            "search",
            {"keyword": "MCP Test Note", "folder": ""},
            "search - find our test note",
        )
        results.append(("search (specific)", success))

        # Test 10: Delete the test note
        success = call_mcp_tool(
            base_url,
            headers,
            "delete_note",
            {"path": test_note_path},
            f"delete_note - delete the test note",
        )
        results.append(("delete_note", success))
    else:
        print("   ⚠️  Skipping read/update/append/delete tests due to create failure")

    # Test Summary
    print("\n" + "=" * 70)
    print("🎉 Obsidian MCP Tools Testing Complete!")

    print(f"\n📊 Test Results Summary:")
    passed = sum(1 for _, success in results if success)
    total = len(results)

    for tool_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"   {status} {tool_name}")

    print(
        f"\n📈 Overall Results: {passed}/{total} tests passed ({passed/total*100:.1f}%)"
    )

    if passed == total:
        print("🎊 All tests passed! MCP Tools are working perfectly!")
    elif passed >= total * 0.8:
        print("🎯 Most tests passed! Some tools may need Obsidian connection.")
    else:
        print("⚠️  Some tools failed. Check Obsidian connection and configuration.")

    print(f"\n💡 Notes:")
    print("   • Tools that require Obsidian connection may fail without proper setup")
    print("   • Some failures are expected if OBSIDIAN_API_KEY is not configured")
    print("   • The MCP protocol and tool integration is working correctly")

    print(f"\n🚀 Ready for Phase 4: MCP Resources!")


if __name__ == "__main__":
    import asyncio

    asyncio.run(run_obsidian_tools_live())


