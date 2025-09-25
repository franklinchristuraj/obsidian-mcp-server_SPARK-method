"""
Obsidian MCP Server - Main Entry Point
"""
import uvicorn
from fastapi import FastAPI, Request, Response, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from dotenv import load_dotenv
import os
import json
import asyncio
from typing import Dict, Any, Optional, AsyncGenerator
from src.auth import verify_api_key
from src.mcp_server import mcp_handler, MCPProtocolHandler

# Load environment variables
load_dotenv()

# Create FastAPI app
app = FastAPI(
    title="Obsidian MCP Server",
    description="Model Context Protocol server for Obsidian vault",
    version="1.0.0",
)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "obsidian-mcp-server"}


@app.get("/")
async def root():
    return {
        "name": "Obsidian MCP Server",
        "version": "1.0.0",
        "endpoints": {"mcp": "/mcp", "health": "/health"},
    }


# JSON-RPC 2.0 Error Codes
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


async def handle_jsonrpc_method(method: str, params: Optional[Any] = None) -> Any:
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


async def create_sse_stream(
    jsonrpc_response: Dict[str, Any],
    result_data: Any = None,
    enable_streaming: bool = False,
) -> AsyncGenerator[str, None]:
    """Create Server-Sent Events stream for MCP responses"""
    # Send initial JSON-RPC response
    yield f"data: {json.dumps(jsonrpc_response)}\n\n"

    # If streaming is enabled and we have large data, stream it
    if enable_streaming and result_data:
        if isinstance(result_data, str) and len(result_data) > 1024:
            # Stream large text content
            async for chunk in mcp_handler.create_streaming_response(result_data):
                yield chunk
        elif isinstance(result_data, list) and len(result_data) > 10:
            # Stream large lists
            async for chunk in mcp_handler.create_streaming_response(result_data):
                yield chunk

    # Send completion signal
    yield "data: [DONE]\n\n"


@app.post("/mcp")
async def mcp_endpoint(request: Request, api_key: str = Depends(verify_api_key)):
    """
    MCP Streamable HTTP endpoint with SSE support
    Accepts JSON-RPC 2.0 requests and returns appropriate responses
    Supports both single JSON responses and Server-Sent Events streaming
    """
    try:
        # Parse request body
        try:
            body = await request.body()
            request_data = json.loads(body.decode())
        except json.JSONDecodeError:
            return JSONResponse(
                content=create_jsonrpc_error("PARSE_ERROR"), status_code=400
            )

        # Validate JSON-RPC format
        validation_error = validate_jsonrpc_request(request_data)
        if validation_error:
            return JSONResponse(content=validation_error, status_code=400)

        request_id = request_data.get("id")
        method = request_data["method"]
        params = request_data.get("params")

        # Check if client wants streaming (via Accept header)
        accept_header = request.headers.get("accept", "")
        wants_streaming = "text/event-stream" in accept_header

        try:
            # Use the new MCP protocol handler
            result = await mcp_handler.handle_request(method, params)

            # Handle notifications (which return None and should not send a response)
            if method.startswith("notifications/") and result is None:
                # For MCP notifications, return a 204 No Content response
                return JSONResponse(content=None, status_code=204)

            response = create_jsonrpc_response(result=result, request_id=request_id)

            # Determine if we should stream the response
            should_stream = wants_streaming and _should_enable_streaming(result)

            if should_stream:
                # Return SSE streaming response
                return StreamingResponse(
                    create_sse_stream(response, result, enable_streaming=True),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Headers": "Content-Type, Authorization",
                    },
                )
            else:
                # Return regular JSON response
                return JSONResponse(content=response)

        except ValueError as e:
            # Method not found
            return JSONResponse(
                content=create_jsonrpc_error("METHOD_NOT_FOUND", str(e), request_id),
                status_code=404,
            )
        except Exception as e:
            # Internal error
            return JSONResponse(
                content=create_jsonrpc_error("INTERNAL_ERROR", str(e), request_id),
                status_code=500,
            )

    except Exception as e:
        # Catch-all for unexpected errors
        return JSONResponse(
            content=create_jsonrpc_error(
                "INTERNAL_ERROR", f"Unexpected error: {str(e)}"
            ),
            status_code=500,
        )


def _should_enable_streaming(result: Any) -> bool:
    """Determine if response should be streamed based on content"""
    if isinstance(result, dict):
        # Check for large text content in various response formats
        if "content" in result:
            content = result["content"]
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and "text" in item:
                        if len(item["text"]) > 1024:  # Stream if text > 1KB
                            return True
            elif isinstance(content, str) and len(content) > 1024:
                return True

        # Check for large result sets
        if "tools" in result and len(result["tools"]) > 10:
            return True
        if "resources" in result and len(result["resources"]) > 10:
            return True

    return False


if __name__ == "__main__":
    host = os.getenv("MCP_HOST", "127.0.0.1")
    port = int(os.getenv("MCP_PORT", "8888"))

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=True,  # Enable auto-reload for development
        log_level="debug",
    )
