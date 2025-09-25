#!/usr/bin/env python3
"""
Simple test for the MCP endpoint using only standard library
"""
import json
import urllib.request
import urllib.parse
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def test_mcp_endpoint():
    """Test the MCP endpoint with simple HTTP requests"""

    # Get configuration
    host = os.getenv("MCP_HOST", "127.0.0.1")
    port = int(os.getenv("MCP_PORT", "8888"))
    api_key = os.getenv("MCP_API_KEY", "test-key")

    base_url = f"http://{host}:{port}"

    print(f"🧪 Testing MCP endpoint at {base_url}/mcp")
    print(f"🔑 Using API key: {api_key[:8]}...")
    print()

    # Test 1: Health check (no auth required)
    print("1️⃣ Testing health endpoint...")
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

    # Test 2: Valid JSON-RPC ping request
    print("\n2️⃣ Testing valid JSON-RPC ping request...")
    ping_request = {"jsonrpc": "2.0", "method": "ping", "id": 1}

    try:
        data = json.dumps(ping_request).encode("utf-8")
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
                print(f"   ✅ Ping successful: {result}")
            else:
                print(f"   ❌ Ping failed: {response.status}")

    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        print(f"   ❌ Ping HTTP error {e.code}: {error_body}")
    except Exception as e:
        print(f"   ❌ Ping error: {e}")

    # Test 3: Invalid JSON-RPC request (missing version)
    print("\n3️⃣ Testing invalid JSON-RPC request...")
    invalid_request = {"method": "ping", "id": 3}

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
            print(f"   ❌ Should have rejected invalid request: {response.status}")

    except urllib.error.HTTPError as e:
        if e.code == 400:
            error_body = json.loads(e.read().decode())
            print(f"   ✅ Correctly rejected invalid request: {error_body}")
        else:
            print(f"   ❌ Wrong error code: {e.code}")
    except Exception as e:
        print(f"   ❌ Invalid request test error: {e}")

    # Test 4: Missing API key
    print("\n4️⃣ Testing missing API key...")
    try:
        data = json.dumps(ping_request).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url}/mcp", data=data, headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(req) as response:
            print(
                f"   ❌ Should have rejected request without API key: {response.status}"
            )

    except urllib.error.HTTPError as e:
        if e.code == 401:
            print("   ✅ Correctly rejected request without API key")
        else:
            print(f"   ❌ Wrong error code: {e.code}")
    except Exception as e:
        print(f"   ❌ Missing API key test error: {e}")

    print("\n🎉 Basic MCP endpoint tests completed!")
    print("\n💡 To run the full test suite:")
    print("   pip3 install httpx")
    print("   python3 test_mcp_endpoint.py")


if __name__ == "__main__":
    test_mcp_endpoint()


