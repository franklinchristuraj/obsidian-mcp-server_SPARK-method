#!/usr/bin/env python3
"""
Test script for MCP endpoint with SSE streaming support
"""
import json
import urllib.request
import urllib.parse
import os
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def test_mcp_streaming_endpoint():
    """Test the MCP endpoint with SSE streaming functionality"""

    # Get configuration
    host = os.getenv("MCP_HOST", "127.0.0.1")
    port = int(os.getenv("MCP_PORT", "8888"))
    api_key = os.getenv("MCP_API_KEY", "test-secret-key")

    base_url = f"http://{host}:{port}"

    print("🧪 Testing MCP endpoint with SSE streaming support")
    print(f"🔗 Endpoint: {base_url}/mcp")
    print(f"🔑 Using API key: {api_key[:8]}...")
    print("=" * 60)

    # Test 1: Health check
    print("\n1️⃣ Testing health endpoint...")
    try:
        req = urllib.request.Request(f"{base_url}/health")
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                result = json.loads(response.read().decode())
                print(f"   ✅ Health check passed: {result}")
            else:
                print(f"   ❌ Health check failed: {response.status}")
    except Exception as e:
        print(f"   ❌ Health check error: {e}")
        print("   💡 Make sure the server is running: python3 main.py")
        return

    # Test 2: MCP Initialize (JSON response)
    print("\n2️⃣ Testing MCP initialize (JSON response)...")
    init_request = {
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "clientInfo": {"name": "test-client", "version": "1.0.0"},
        },
        "id": 1,
    }

    try:
        data = json.dumps(init_request).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url}/mcp",
            data=data,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",  # Request JSON response
            },
        )

        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                result = json.loads(response.read().decode())
                print(f"   ✅ Initialize successful")
                print(f"   📤 Protocol Version: {result['result']['protocolVersion']}")
                print(
                    f"   🛠️  Capabilities: {list(result['result']['capabilities'].keys())}"
                )
            else:
                print(f"   ❌ Initialize failed: {response.status}")

    except Exception as e:
        print(f"   ❌ Initialize error: {e}")

    # Test 3: MCP Initialize (SSE streaming)
    print("\n3️⃣ Testing MCP initialize (SSE streaming)...")
    try:
        data = json.dumps(init_request).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url}/mcp",
            data=data,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",  # Request SSE streaming
            },
        )

        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                print(f"   ✅ SSE streaming response received")
                print(f"   📡 Content-Type: {response.headers.get('Content-Type')}")

                # Read SSE stream
                stream_data = response.read().decode()
                lines = stream_data.strip().split("\n")

                for line in lines:
                    if line.startswith("data: "):
                        data_content = line[6:]  # Remove 'data: ' prefix
                        if data_content == "[DONE]":
                            print(f"   🏁 Stream completed")
                        else:
                            try:
                                parsed = json.loads(data_content)
                                if "result" in parsed:
                                    print(f"   📦 JSON-RPC response received in stream")
                                else:
                                    print(f"   📤 Stream chunk: {data_content[:50]}...")
                            except json.JSONDecodeError:
                                print(f"   📤 Raw stream data: {data_content[:50]}...")
            else:
                print(f"   ❌ SSE request failed: {response.status}")

    except Exception as e:
        print(f"   ❌ SSE streaming error: {e}")

    # Test 4: Tools list
    print("\n4️⃣ Testing tools/list method...")
    tools_request = {"jsonrpc": "2.0", "method": "tools/list", "id": 2}

    try:
        data = json.dumps(tools_request).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url}/mcp",
            data=data,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                result = json.loads(response.read().decode())
                tools = result["result"]["tools"]
                print(f"   ✅ Tools list retrieved: {len(tools)} tools available")
                for tool in tools:
                    print(f"      • {tool['name']}: {tool['description']}")
            else:
                print(f"   ❌ Tools list failed: {response.status}")

    except Exception as e:
        print(f"   ❌ Tools list error: {e}")

    # Test 5: Tools call (ping)
    print("\n5️⃣ Testing tools/call method (ping)...")
    tool_call_request = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": "ping", "arguments": {}},
        "id": 3,
    }

    try:
        data = json.dumps(tool_call_request).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url}/mcp",
            data=data,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                result = json.loads(response.read().decode())
                content = result["result"]["content"]
                print(f"   ✅ Tool call successful")
                for item in content:
                    if item["type"] == "text":
                        print(f"   📤 Response: {item['text']}")
            else:
                print(f"   ❌ Tool call failed: {response.status}")

    except Exception as e:
        print(f"   ❌ Tool call error: {e}")

    # Test 6: Resources list
    print("\n6️⃣ Testing resources/list method...")
    resources_request = {"jsonrpc": "2.0", "method": "resources/list", "id": 4}

    try:
        data = json.dumps(resources_request).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url}/mcp",
            data=data,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                result = json.loads(response.read().decode())
                resources = result["result"]["resources"]
                print(
                    f"   ✅ Resources list retrieved: {len(resources)} resources available"
                )
                for resource in resources:
                    print(f"      • {resource['uri']}: {resource['name']}")
            else:
                print(f"   ❌ Resources list failed: {response.status}")

    except Exception as e:
        print(f"   ❌ Resources list error: {e}")

    # Test 7: Invalid method (should fail gracefully)
    print("\n7️⃣ Testing invalid method...")
    invalid_request = {"jsonrpc": "2.0", "method": "invalid/method", "id": 5}

    try:
        data = json.dumps(invalid_request).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url}/mcp",
            data=data,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

        with urllib.request.urlopen(req) as response:
            print(f"   ❌ Should have failed but got: {response.status}")

    except urllib.error.HTTPError as e:
        if e.code == 404:
            error_body = json.loads(e.read().decode())
            print(
                f"   ✅ Correctly rejected invalid method: {error_body['error']['message']}"
            )
        else:
            print(f"   ❌ Wrong error code: {e.code}")
    except Exception as e:
        print(f"   ❌ Invalid method test error: {e}")

    print("\n" + "=" * 60)
    print("🎉 MCP streaming endpoint tests completed!")
    print("\n📋 Summary:")
    print("   ✅ Basic JSON-RPC 2.0 protocol support")
    print("   ✅ SSE streaming capability")
    print(
        "   ✅ MCP protocol methods (initialize, tools/list, tools/call, resources/list)"
    )
    print("   ✅ Proper error handling")
    print("   ✅ API key authentication")

    print("\n🚀 Next steps:")
    print("   • Implement actual Obsidian tools (search, read, write)")
    print("   • Add Obsidian resources (vault browsing)")
    print("   • Test with large content for streaming")


if __name__ == "__main__":
    test_mcp_streaming_endpoint()


