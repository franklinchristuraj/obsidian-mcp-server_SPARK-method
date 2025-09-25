#!/usr/bin/env python3
"""
Test script for the MCP endpoint
"""
import asyncio
import json
import os
import sys
from dotenv import load_dotenv
import httpx

# Load environment variables
load_dotenv()


async def test_mcp_endpoint():
    """Test the MCP endpoint with various JSON-RPC requests"""

    # Get configuration
    host = os.getenv("MCP_HOST", "127.0.0.1")
    port = int(os.getenv("MCP_PORT", "8888"))
    api_key = os.getenv("MCP_API_KEY")

    if not api_key:
        print("❌ Error: MCP_API_KEY environment variable not set")
        sys.exit(1)

    base_url = f"http://{host}:{port}"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    print(f"🧪 Testing MCP endpoint at {base_url}/mcp")
    print(f"🔑 Using API key: {api_key[:8]}...")
    print()

    async with httpx.AsyncClient() as client:
        # Test 1: Health check
        print("1️⃣ Testing health endpoint...")
        try:
            response = await client.get(f"{base_url}/health")
            if response.status_code == 200:
                print("   ✅ Health check passed")
            else:
                print(f"   ❌ Health check failed: {response.status_code}")
        except Exception as e:
            print(f"   ❌ Health check error: {e}")
            return

        # Test 2: Valid JSON-RPC ping request
        print("\n2️⃣ Testing valid JSON-RPC ping request...")
        ping_request = {"jsonrpc": "2.0", "method": "ping", "id": 1}

        try:
            response = await client.post(
                f"{base_url}/mcp", headers=headers, json=ping_request
            )

            if response.status_code == 200:
                result = response.json()
                print(f"   ✅ Ping successful: {result}")
            else:
                print(f"   ❌ Ping failed: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"   ❌ Ping error: {e}")

        # Test 3: Valid JSON-RPC initialize request
        print("\n3️⃣ Testing valid JSON-RPC initialize request...")
        init_request = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0.0"},
            },
            "id": 2,
        }

        try:
            response = await client.post(
                f"{base_url}/mcp", headers=headers, json=init_request
            )

            if response.status_code == 200:
                result = response.json()
                print(f"   ✅ Initialize successful: {json.dumps(result, indent=2)}")
            else:
                print(
                    f"   ❌ Initialize failed: {response.status_code} - {response.text}"
                )
        except Exception as e:
            print(f"   ❌ Initialize error: {e}")

        # Test 4: Invalid JSON-RPC request (missing version)
        print("\n4️⃣ Testing invalid JSON-RPC request (missing version)...")
        invalid_request = {"method": "ping", "id": 3}

        try:
            response = await client.post(
                f"{base_url}/mcp", headers=headers, json=invalid_request
            )

            if response.status_code == 400:
                result = response.json()
                print(f"   ✅ Correctly rejected invalid request: {result}")
            else:
                print(
                    f"   ❌ Should have rejected invalid request: {response.status_code}"
                )
        except Exception as e:
            print(f"   ❌ Invalid request test error: {e}")

        # Test 5: Method not found
        print("\n5️⃣ Testing method not found...")
        unknown_request = {"jsonrpc": "2.0", "method": "unknown_method", "id": 4}

        try:
            response = await client.post(
                f"{base_url}/mcp", headers=headers, json=unknown_request
            )

            if response.status_code == 404:
                result = response.json()
                print(f"   ✅ Correctly returned method not found: {result}")
            else:
                print(
                    f"   ❌ Should have returned method not found: {response.status_code}"
                )
        except Exception as e:
            print(f"   ❌ Method not found test error: {e}")

        # Test 6: Invalid JSON
        print("\n6️⃣ Testing invalid JSON...")
        try:
            response = await client.post(
                f"{base_url}/mcp", headers=headers, content="invalid json"
            )

            if response.status_code == 400:
                result = response.json()
                print(f"   ✅ Correctly rejected invalid JSON: {result}")
            else:
                print(f"   ❌ Should have rejected invalid JSON: {response.status_code}")
        except Exception as e:
            print(f"   ❌ Invalid JSON test error: {e}")

        # Test 7: Missing API key
        print("\n7️⃣ Testing missing API key...")
        try:
            response = await client.post(
                f"{base_url}/mcp",
                headers={"Content-Type": "application/json"},
                json=ping_request,
            )

            if response.status_code == 401:
                print("   ✅ Correctly rejected request without API key")
            else:
                print(
                    f"   ❌ Should have rejected request without API key: {response.status_code}"
                )
        except Exception as e:
            print(f"   ❌ Missing API key test error: {e}")

    print("\n🎉 MCP endpoint tests completed!")


if __name__ == "__main__":
    asyncio.run(test_mcp_endpoint())
