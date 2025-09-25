# MCP Endpoint Implementation

## Overview

The MCP (Model Context Protocol) endpoint at `POST /mcp` has been implemented according to the MCP Streamable HTTP specification. This endpoint accepts JSON-RPC 2.0 requests, validates API keys, and returns compliant JSON-RPC responses.

## Features

### ✅ JSON-RPC 2.0 Compliance
- Full JSON-RPC 2.0 request validation
- Proper error codes (-32700 to -32603)
- Structured error responses
- Request ID preservation

### ✅ API Key Authentication
- Uses `src/auth.py` for validation
- Bearer token authentication
- Proper 401 responses for invalid/missing keys

### ✅ MCP Protocol Support
- `ping` method for connectivity testing
- `initialize` method for protocol handshake
- Extensible method handler system

### ✅ Error Handling
- Parse errors for invalid JSON
- Invalid request format detection
- Method not found responses
- Internal error handling

## API Usage

### Endpoint
```
POST /mcp
Content-Type: application/json
Authorization: Bearer <your-api-key>
```

### Request Format
```json
{
  "jsonrpc": "2.0",
  "method": "ping",
  "id": 1
}
```

### Response Format
```json
{
  "jsonrpc": "2.0",
  "result": {
    "message": "pong",
    "timestamp": "2025-09-22T00:00:00Z"
  },
  "id": 1
}
```

## Supported Methods

### `ping`
Simple connectivity test.

**Request:**
```json
{
  "jsonrpc": "2.0",
  "method": "ping",
  "id": 1
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "result": {
    "message": "pong",
    "timestamp": "2025-09-22T00:00:00Z"
  },
  "id": 1
}
```

### `initialize`
MCP protocol initialization handshake.

**Request:**
```json
{
  "jsonrpc": "2.0",
  "method": "initialize",
  "params": {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {
      "name": "test-client",
      "version": "1.0.0"
    }
  },
  "id": 2
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "result": {
    "protocolVersion": "2024-11-05",
    "capabilities": {
      "tools": {},
      "resources": {},
      "prompts": {},
      "logging": {}
    },
    "serverInfo": {
      "name": "obsidian-mcp-server",
      "version": "1.0.0"
    }
  },
  "id": 2
}
```

## Error Responses

### Parse Error (-32700)
```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32700,
    "message": "Parse error"
  },
  "id": null
}
```

### Invalid Request (-32600)
```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32600,
    "message": "Invalid Request",
    "data": "Invalid or missing jsonrpc version"
  },
  "id": 1
}
```

### Method Not Found (-32601)
```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32601,
    "message": "Method not found",
    "data": "Method not found: unknown_method"
  },
  "id": 1
}
```

## Testing

Run the test script to verify endpoint functionality:

```bash
# Set environment variables
export MCP_API_KEY="your-secret-key"
export MCP_HOST="127.0.0.1"
export MCP_PORT="8888"

# Run tests
python3 test_mcp_endpoint.py
```

The test script will verify:
1. Health endpoint accessibility
2. Valid JSON-RPC requests
3. Error handling for invalid requests
4. Authentication validation
5. Method not found responses

## Security Features

- **API Key Validation**: All requests require valid Bearer token
- **Input Validation**: JSON-RPC format strictly validated
- **Error Isolation**: Internal errors don't expose sensitive data
- **CORS Ready**: Can be extended with CORS headers if needed

## Extending the Endpoint

To add new MCP methods, extend the `handle_jsonrpc_method` function in `main.py`:

```python
async def handle_jsonrpc_method(method: str, params: Optional[Any] = None) -> Any:
    if method == "your_new_method":
        # Implement your method logic
        return {"result": "your_response"}
    # ... existing methods
```

## Configuration

Set the following environment variables:

```bash
MCP_HOST=127.0.0.1      # Server host
MCP_PORT=8888           # Server port  
MCP_API_KEY=secret-key  # API authentication key
```
