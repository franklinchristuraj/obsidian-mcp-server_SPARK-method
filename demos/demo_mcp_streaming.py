#!/usr/bin/env python3
"""
Demo script showing MCP SSE streaming capabilities with simulated large data
"""
import json
import os
import asyncio
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from src.mcp_server import MCPProtocolHandler, MCPTool

# Load environment variables
load_dotenv()


class StreamingDemo:
    """Demo class to show streaming capabilities"""

    def __init__(self):
        self.mcp_handler = MCPProtocolHandler()
        self._add_demo_tools()

    def _add_demo_tools(self):
        """Add demo tools that generate large responses"""

        # Large text generator tool
        large_text_tool = MCPTool(
            name="generate_large_text",
            description="Generate large text content to demonstrate streaming",
            inputSchema={
                "type": "object",
                "properties": {
                    "size": {
                        "type": "integer",
                        "description": "Size of text to generate (in KB)",
                        "default": 5,
                    }
                },
                "additionalProperties": False,
            },
        )

        # Search results simulator
        search_tool = MCPTool(
            name="simulate_search",
            description="Simulate search results with many items",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "count": {
                        "type": "integer",
                        "description": "Number of results to return",
                        "default": 20,
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        )

        self.mcp_handler.add_tool(large_text_tool)
        self.mcp_handler.add_tool(search_tool)

    async def handle_demo_tool_call(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle demo tool calls"""

        if tool_name == "generate_large_text":
            size_kb = arguments.get("size", 5)
            # Generate large text (size_kb * 1024 characters)
            text_size = size_kb * 1024
            large_text = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * (
                text_size // 56
            )
            large_text = large_text[:text_size]  # Trim to exact size

            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Generated {len(large_text)} characters of text:\n\n{large_text}",
                    }
                ]
            }

        elif tool_name == "simulate_search":
            query = arguments.get("query", "")
            count = arguments.get("count", 20)

            # Generate simulated search results
            results = []
            for i in range(count):
                results.append(
                    f"Result {i+1}: Note about {query} - This is a detailed description of the search result that contains information about {query}. Created on 2024-01-{(i % 28) + 1:02d}."
                )

            result_text = f"Found {count} results for '{query}':\n\n" + "\n".join(
                results
            )

            return {"content": [{"type": "text", "text": result_text}]}

        return {"error": f"Unknown demo tool: {tool_name}"}


async def demo_streaming():
    """Demonstrate streaming capabilities"""

    print("🚀 MCP SSE Streaming Demo")
    print("=" * 50)

    demo = StreamingDemo()

    # Override the tool call handler for demo purposes
    original_handle_tools_call = demo.mcp_handler._handle_tools_call

    async def demo_handle_tools_call(params):
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if tool_name in ["generate_large_text", "simulate_search"]:
            return await demo.handle_demo_tool_call(tool_name, arguments)
        else:
            return await original_handle_tools_call(params)

    demo.mcp_handler._handle_tools_call = demo_handle_tools_call

    # Test 1: List available tools
    print("\n1️⃣ Listing available tools...")
    tools_result = await demo.mcp_handler.handle_request("tools/list")
    print(f"   ✅ Found {len(tools_result['tools'])} tools:")
    for tool in tools_result["tools"]:
        print(f"      • {tool['name']}: {tool['description']}")

    # Test 2: Generate large text (will trigger streaming)
    print("\n2️⃣ Testing large text generation (5KB)...")
    large_text_result = await demo.mcp_handler.handle_request(
        "tools/call", {"name": "generate_large_text", "arguments": {"size": 5}}
    )

    content_text = large_text_result["content"][0]["text"]
    print(f"   ✅ Generated {len(content_text)} characters")
    print(f"   📤 Preview: {content_text[:100]}...")

    # Test 3: Simulate streaming for large text
    print("\n3️⃣ Simulating SSE streaming for large text...")
    chunk_count = 0
    async for chunk in demo.mcp_handler.create_streaming_response(
        content_text, chunk_size=512
    ):
        chunk_count += 1
        if chunk.startswith("data: "):
            chunk_data = chunk[6:].strip()
            if chunk_data != "[DONE]":
                try:
                    parsed = json.loads(chunk_data)
                    if parsed.get("type") == "content":
                        print(
                            f"   📦 Chunk {chunk_count}: {len(parsed.get('chunk', ''))} chars, Complete: {parsed.get('isComplete', False)}"
                        )
                    elif parsed.get("type") == "complete":
                        print(f"   🏁 Streaming completed")
                except json.JSONDecodeError:
                    print(f"   📤 Raw chunk: {chunk_data[:50]}...")

    # Test 4: Simulate search with many results
    print("\n4️⃣ Testing search simulation (25 results)...")
    search_result = await demo.mcp_handler.handle_request(
        "tools/call",
        {
            "name": "simulate_search",
            "arguments": {"query": "machine learning", "count": 25},
        },
    )

    search_text = search_result["content"][0]["text"]
    lines = search_text.split("\n")
    print(f"   ✅ Generated search with {len(lines)} lines")
    print(f"   📤 Preview: {lines[0]}")

    # Test 5: Simulate streaming for search results
    print("\n5️⃣ Simulating SSE streaming for search results...")
    results_list = search_text.split("\n")[2:]  # Skip header lines
    chunk_count = 0
    async for chunk in demo.mcp_handler.create_streaming_response(results_list):
        chunk_count += 1
        if chunk.startswith("data: "):
            chunk_data = chunk[6:].strip()
            try:
                parsed = json.loads(chunk_data)
                if parsed.get("type") == "list_item":
                    item_preview = parsed.get("item", "")[:50]
                    print(f"   📦 Item {parsed.get('index', '?')}: {item_preview}...")
                elif parsed.get("type") == "complete":
                    print(f"   🏁 List streaming completed")
            except json.JSONDecodeError:
                pass

    print("\n" + "=" * 50)
    print("🎉 Streaming demo completed!")
    print("\n📋 Key Features Demonstrated:")
    print("   ✅ Large text content streaming (chunked)")
    print("   ✅ List/array streaming (item by item)")
    print("   ✅ Automatic streaming detection")
    print("   ✅ SSE format compliance")
    print("   ✅ Completion signals")

    print("\n🔧 Technical Details:")
    print(f"   • Text chunked into 512-byte segments")
    print(f"   • Lists streamed item by item")
    print(f"   • JSON-RPC responses wrapped in SSE format")
    print(f"   • Completion markers sent at end")

    print("\n🚀 Ready for real Obsidian integration!")


if __name__ == "__main__":
    asyncio.run(demo_streaming())


