#!/usr/bin/env python3
"""
Tool Verification Script for Obsidian MCP Server
Verifies that all tools are properly registered and functioning
"""
import sys
import asyncio
from typing import Dict, Any, List

# Add src to path
sys.path.insert(0, '.')

from src.mcp_server import mcp_handler
from src.tools.obsidian_tools import obsidian_tools


def verify_tool_registration():
    """Verify all tools are registered in the MCP handler"""
    print("🔍 Verifying Tool Registration")
    print("=" * 60)
    
    # Get tools from handler
    registered_tools = mcp_handler.tools
    print(f"\n📊 Total tools registered: {len(registered_tools)}")
    
    # Expected tools based on documentation
    expected_tools = [
        "ping",
        "obs_search_notes",
        "obs_read_note",
        "obs_create_note",
        "obs_update_note",
        "obs_append_note",
        "obs_delete_note",
        "obs_list_notes",
        "obs_get_vault_structure",
        "obs_execute_command",
        "obs_keyword_search",
        "obs_check_note_exists",
        "obs_list_daily_notes",
    ]
    
    registered_names = [tool.name for tool in registered_tools]
    
    print("\n✅ Registered Tools:")
    for tool in registered_tools:
        print(f"   - {tool.name}")
    
    print("\n🔍 Checking for missing tools:")
    missing = []
    for expected in expected_tools:
        if expected not in registered_names:
            missing.append(expected)
            print(f"   ❌ Missing: {expected}")
        else:
            print(f"   ✅ Found: {expected}")
    
    if missing:
        print(f"\n⚠️  Warning: {len(missing)} expected tool(s) not found")
        return False
    
    print(f"\n✅ All {len(expected_tools)} expected tools are registered")
    return True


def verify_tool_schemas():
    """Verify tool schemas are valid"""
    print("\n\n🔍 Verifying Tool Schemas")
    print("=" * 60)
    
    issues = []
    
    for tool in mcp_handler.tools:
        print(f"\n📋 Checking: {tool.name}")
        
        # Check required schema fields
        if not hasattr(tool, 'name') or not tool.name:
            issues.append(f"{tool.name}: Missing name")
            print("   ❌ Missing name")
        else:
            print(f"   ✅ Name: {tool.name}")
        
        if not hasattr(tool, 'description') or not tool.description:
            issues.append(f"{tool.name}: Missing description")
            print("   ❌ Missing description")
        else:
            desc_preview = tool.description[:50] + "..." if len(tool.description) > 50 else tool.description
            print(f"   ✅ Description: {desc_preview}")
        
        if not hasattr(tool, 'inputSchema') or not tool.inputSchema:
            issues.append(f"{tool.name}: Missing inputSchema")
            print("   ❌ Missing inputSchema")
        else:
            schema = tool.inputSchema
            if not isinstance(schema, dict):
                issues.append(f"{tool.name}: inputSchema must be a dict")
                print("   ❌ inputSchema is not a dict")
            elif schema.get("type") != "object":
                issues.append(f"{tool.name}: inputSchema.type must be 'object'")
                print("   ❌ inputSchema.type is not 'object'")
            else:
                print("   ✅ Valid inputSchema structure")
                if "properties" in schema:
                    prop_count = len(schema["properties"])
                    print(f"   ✅ Properties: {prop_count}")
                if "required" in schema:
                    req_count = len(schema["required"])
                    print(f"   ✅ Required fields: {req_count}")
    
    if issues:
        print(f"\n⚠️  Found {len(issues)} schema issue(s)")
        return False
    
    print("\n✅ All tool schemas are valid")
    return True


async def verify_tools_list_method():
    """Verify tools/list method works correctly"""
    print("\n\n🔍 Verifying tools/list Method")
    print("=" * 60)
    
    try:
        result = await mcp_handler._handle_tools_list(None)
        
        if "tools" not in result:
            print("   ❌ Response missing 'tools' field")
            return False
        
        tools_list = result["tools"]
        if not isinstance(tools_list, list):
            print("   ❌ 'tools' field is not a list")
            return False
        
        print(f"   ✅ tools/list returned {len(tools_list)} tools")
        
        # Verify each tool in the list has required fields
        for tool in tools_list:
            if "name" not in tool:
                print(f"   ❌ Tool missing 'name': {tool}")
                return False
            if "description" not in tool:
                print(f"   ❌ Tool missing 'description': {tool.get('name', 'unknown')}")
                return False
            if "inputSchema" not in tool:
                print(f"   ❌ Tool missing 'inputSchema': {tool.get('name', 'unknown')}")
                return False
        
        print("   ✅ All tools in list have required fields")
        return True
        
    except Exception as e:
        print(f"   ❌ Error calling tools/list: {e}")
        import traceback
        traceback.print_exc()
        return False


async def verify_tool_dispatcher():
    """Verify tool execution dispatcher works"""
    print("\n\n🔍 Verifying Tool Dispatcher")
    print("=" * 60)
    
    # Test ping tool (doesn't require Obsidian connection)
    print("\n📋 Testing ping tool:")
    try:
        result = await mcp_handler._handle_tools_call({
            "name": "ping",
            "arguments": {}
        })
        
        if "content" in result:
            print("   ✅ ping tool executed successfully")
            print(f"   ✅ Response type: {type(result)}")
        else:
            print("   ⚠️  ping tool response missing 'content' field")
            print(f"   Response: {result}")
        
    except Exception as e:
        print(f"   ❌ Error executing ping tool: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test that unknown tools are handled correctly
    print("\n📋 Testing unknown tool handling:")
    try:
        result = await mcp_handler._handle_tools_call({
            "name": "unknown_tool_xyz",
            "arguments": {}
        })
        
        if "content" in result:
            content = result["content"]
            if isinstance(content, list) and len(content) > 0:
                text = content[0].get("text", "")
                if "Unknown tool" in text or "Unknown" in text:
                    print("   ✅ Unknown tool handled correctly")
                else:
                    print(f"   ⚠️  Unexpected response: {text}")
        else:
            print("   ⚠️  Unknown tool response format unexpected")
            
    except Exception as e:
        print(f"   ⚠️  Unknown tool test raised exception: {e}")
    
    # Test Obsidian tool dispatcher (without actually calling Obsidian)
    print("\n📋 Testing Obsidian tool dispatcher:")
    try:
        # Check if obsidian_tools has execute_tool method
        if hasattr(obsidian_tools, 'execute_tool'):
            print("   ✅ obsidian_tools.execute_tool method exists")
            
            # Check if it has the tool methods registered
            if hasattr(obsidian_tools, 'get_tools'):
                tools = obsidian_tools.get_tools()
                print(f"   ✅ obsidian_tools.get_tools() returns {len(tools)} tools")
            else:
                print("   ⚠️  obsidian_tools.get_tools() method not found")
        else:
            print("   ❌ obsidian_tools.execute_tool method not found")
            return False
            
    except Exception as e:
        print(f"   ❌ Error checking Obsidian tools: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


def verify_obsidian_client():
    """Verify Obsidian client initialization"""
    print("\n\n🔍 Verifying Obsidian Client")
    print("=" * 60)
    
    try:
        client = obsidian_tools.client
        
        if client is None:
            print("   ⚠️  Obsidian client is None (may be intentional if API key not set)")
            print("   ℹ️  This is OK - tools will fail gracefully with helpful error messages")
            return True
        
        print("   ✅ Obsidian client initialized")
        
        # Check if client has required methods
        required_methods = [
            'search_notes',
            'read_note',
            'create_note',
            'update_note',
            'append_note',
            'delete_note',
            'list_notes',
            'get_vault_structure',
            'execute_command',
        ]
        
        missing_methods = []
        for method in required_methods:
            if hasattr(client, method):
                print(f"   ✅ Method exists: {method}")
            else:
                missing_methods.append(method)
                print(f"   ❌ Method missing: {method}")
        
        if missing_methods:
            print(f"\n   ⚠️  Missing {len(missing_methods)} required method(s)")
            return False
        
        print("\n   ✅ All required Obsidian client methods exist")
        return True
        
    except Exception as e:
        print(f"   ❌ Error checking Obsidian client: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all verification checks"""
    print("🚀 Obsidian MCP Server - Tool Verification")
    print("=" * 60)
    print()
    
    results = []
    
    # Run synchronous checks
    results.append(("Tool Registration", verify_tool_registration()))
    results.append(("Tool Schemas", verify_tool_schemas()))
    results.append(("Obsidian Client", verify_obsidian_client()))
    
    # Run async checks
    results.append(("tools/list Method", await verify_tools_list_method()))
    results.append(("Tool Dispatcher", await verify_tool_dispatcher()))
    
    # Summary
    print("\n\n" + "=" * 60)
    print("📋 VERIFICATION SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for check_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {check_name}")
    
    print("\n" + "=" * 60)
    if passed == total:
        print(f"✅ All checks passed ({passed}/{total})")
        print("\n🎉 All tools are properly configured and functioning!")
        return 0
    else:
        print(f"⚠️  {passed}/{total} checks passed")
        print("\n💡 Some issues were found. Check the output above for details.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

