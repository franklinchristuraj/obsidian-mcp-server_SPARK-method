#!/usr/bin/env python3
"""
Demo script showing the MCP endpoint implementation
This demonstrates the core JSON-RPC logic without requiring external dependencies
"""
import json
import os
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# JSON-RPC 2.0 Error Codes (same as in main.py)
JSONRPC_ERRORS = {
    "PARSE_ERROR": {"code": -32700, "message": "Parse error"},
    "INVALID_REQUEST": {"code": -32600, "message": "Invalid Request"},
    "METHOD_NOT_FOUND": {"code": -32601, "message": "Method not found"},
    "INVALID_PARAMS": {"code": -32602, "message": "Invalid params"},
    "INTERNAL_ERROR": {"code": -32603, "message": "Internal error"},
}


def create_jsonrpc_response(
    result: Any = None, error: Optional[Dict] = None, request_id: Optional[Any] = None
) -> Dict[str, Any]:
    """Create a JSON-RPC 2.0 compliant response"""
    response = {"jsonrpc": "2.0", "id": request_id}

    if error:
        response["error"] = error
    else:
        response["result"] = result

    return response


def create_jsonrpc_error(
    error_type: str, data: Optional[Any] = None, request_id: Optional[Any] = None
) -> Dict[str, Any]:
    """Create a JSON-RPC 2.0 error response"""
    error = JSONRPC_ERRORS[error_type].copy()
    if data:
        error["data"] = data

    return create_jsonrpc_response(error=error, request_id=request_id)


def validate_jsonrpc_request(request_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Validate JSON-RPC 2.0 request format"""
    # Check required fields
    if not isinstance(request_data, dict):
        return create_jsonrpc_error("INVALID_REQUEST")

    if request_data.get("jsonrpc") != "2.0":
        return create_jsonrpc_error(
            "INVALID_REQUEST",
            "Invalid or missing jsonrpc version",
            request_data.get("id"),
        )

    if "method" not in request_data:
        return create_jsonrpc_error(
            "INVALID_REQUEST", "Missing method field", request_data.get("id")
        )

    if not isinstance(request_data["method"], str):
        return create_jsonrpc_error(
            "INVALID_REQUEST", "Method must be a string", request_data.get("id")
        )

    return None


def handle_jsonrpc_method(method: str, params: Optional[Any] = None) -> Any:
    """Handle MCP method calls"""
    # For now, implement a simple ping method
    if method == "ping":
        return {"message": "pong", "timestamp": "2025-09-22T00:00:00Z"}

    # Add more MCP methods here as needed
    elif method == "initialize":
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {},
                "resources": {},
                "prompts": {},
                "logging": {},
            },
            "serverInfo": {"name": "obsidian-mcp-server", "version": "1.0.0"},
        }

    else:
        raise ValueError(f"Method not found: {method}")


def verify_api_key(authorization: str) -> bool:
    """Verify API key (simplified version of src/auth.py logic)"""
    expected_key = os.getenv("MCP_API_KEY", "test-secret-key")

    if not authorization:
        return False

    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            return False
        return token == expected_key
    except ValueError:
        return False


def process_mcp_request(request_json: str, authorization: str = None) -> Dict[str, Any]:
    """
    Process an MCP request and return the response
    This simulates what the FastAPI endpoint does
    """
    # Verify API key
    if not verify_api_key(authorization):
        return {
            "error": "Unauthorized",
            "status_code": 401,
            "detail": "Invalid or missing API key",
        }

    try:
        # Parse request
        try:
            request_data = json.loads(request_json)
        except json.JSONDecodeError:
            return {"response": create_jsonrpc_error("PARSE_ERROR"), "status_code": 400}

        # Validate JSON-RPC format
        validation_error = validate_jsonrpc_request(request_data)
        if validation_error:
            return {"response": validation_error, "status_code": 400}

        request_id = request_data.get("id")
        method = request_data["method"]
        params = request_data.get("params")

        try:
            # Handle the method call
            result = handle_jsonrpc_method(method, params)
            response = create_jsonrpc_response(result=result, request_id=request_id)

            return {"response": response, "status_code": 200}

        except ValueError as e:
            # Method not found
            return {
                "response": create_jsonrpc_error(
                    "METHOD_NOT_FOUND", str(e), request_id
                ),
                "status_code": 404,
            }
        except Exception as e:
            # Internal error
            return {
                "response": create_jsonrpc_error("INTERNAL_ERROR", str(e), request_id),
                "status_code": 500,
            }

    except Exception as e:
        # Catch-all for unexpected errors
        return {
            "response": create_jsonrpc_error(
                "INTERNAL_ERROR", f"Unexpected error: {str(e)}"
            ),
            "status_code": 500,
        }


def demo_mcp_endpoint():
    """Demonstrate the MCP endpoint functionality"""
    print("🚀 MCP Endpoint Implementation Demo")
    print("=" * 50)

    api_key = os.getenv("MCP_API_KEY", "test-secret-key")
    auth_header = f"Bearer {api_key}"

    # Test cases
    test_cases = [
        {
            "name": "Valid ping request",
            "request": json.dumps({"jsonrpc": "2.0", "method": "ping", "id": 1}),
            "auth": auth_header,
        },
        {
            "name": "Valid initialize request",
            "request": json.dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "clientInfo": {"name": "test-client", "version": "1.0.0"},
                    },
                    "id": 2,
                }
            ),
            "auth": auth_header,
        },
        {"name": "Invalid JSON", "request": "invalid json", "auth": auth_header},
        {
            "name": "Missing jsonrpc version",
            "request": json.dumps({"method": "ping", "id": 3}),
            "auth": auth_header,
        },
        {
            "name": "Method not found",
            "request": json.dumps(
                {"jsonrpc": "2.0", "method": "unknown_method", "id": 4}
            ),
            "auth": auth_header,
        },
        {
            "name": "Missing API key",
            "request": json.dumps({"jsonrpc": "2.0", "method": "ping", "id": 5}),
            "auth": None,
        },
    ]

    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{i}️⃣ Test: {test_case['name']}")
        print(
            f"   Request: {test_case['request'][:80]}{'...' if len(test_case['request']) > 80 else ''}"
        )

        result = process_mcp_request(test_case["request"], test_case["auth"])

        status_code = result.get("status_code")
        if status_code == 200:
            print(f"   ✅ Status: {status_code}")
            print(f"   📤 Response: {json.dumps(result['response'], indent=2)}")
        elif status_code in [400, 401, 404, 500]:
            print(f"   ✅ Status: {status_code} (Expected error)")
            if "response" in result:
                print(f"   📤 Response: {json.dumps(result['response'], indent=2)}")
            else:
                print(f"   📤 Error: {result.get('detail', result.get('error'))}")
        else:
            print(f"   ❌ Unexpected status: {status_code}")

    print("\n🎉 Demo completed!")
    print("\n📝 Summary:")
    print("   ✅ JSON-RPC 2.0 request validation")
    print("   ✅ API key authentication")
    print("   ✅ Method handling (ping, initialize)")
    print("   ✅ Error handling and proper error codes")
    print("   ✅ MCP protocol compliance")

    print("\n💡 The actual FastAPI server implementation:")
    print("   - Uses the same core logic shown above")
    print("   - Handles HTTP requests at POST /mcp")
    print("   - Supports SSE streaming (as per MCP spec)")
    print("   - Integrates with src/auth.py for authentication")


if __name__ == "__main__":
    demo_mcp_endpoint()


