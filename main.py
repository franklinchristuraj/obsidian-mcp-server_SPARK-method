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
import time
import hashlib
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


@app.get("/authorize")
async def oauth_authorize(
    request: Request,
    response_type: str = None,
    client_id: str = None,
    redirect_uri: str = None,
    code_challenge: str = None,
    code_challenge_method: str = None,
    state: str = None,
    scope: str = None,
):
    """
    OAuth 2.0 Authorization endpoint for Claude.ai connectors
    Implements simplified OAuth flow that returns authorization code
    """
    from urllib.parse import unquote
    
    # Decode URL-encoded client_id (Claude.ai sends "Obsidian+MCP+Server" URL-encoded)
    if client_id:
        client_id = unquote(client_id)
    
    expected_key = os.getenv("MCP_API_KEY")
    
    # Claude.ai sends the connector name as client_id, not the API key
    # We'll accept any client_id and generate a code, then verify in token endpoint
    # For simplified flow, accept any client_id and generate authorization code
    if client_id:
        # Generate authorization code
        code_data = f"{client_id}:{time.time()}:{code_challenge or ''}"
        auth_code = hashlib.sha256(code_data.encode()).hexdigest()[:32]
        
        # Store code temporarily (in production, use Redis or database)
        # For now, accept any code in token endpoint if client_id matches
        
        # Redirect back to Claude.ai with authorization code
        if redirect_uri:
            redirect_url = f"{redirect_uri}?code={auth_code}&state={state or ''}"
            return Response(status_code=302, headers={"Location": redirect_url})
        else:
            return {"code": auth_code, "state": state}
    
    # Return error if no client_id
    return JSONResponse(
        content={"error": "invalid_request", "error_description": "Missing client_id"},
        status_code=400,
    )


@app.post("/token")
async def oauth_token(
    request: Request,
    grant_type: str = None,
    code: str = None,
    redirect_uri: str = None,
    client_id: str = None,
    code_verifier: str = None,
    scope: str = None,
):
    """
    OAuth 2.0 Token endpoint for Claude.ai connectors
    Exchanges authorization code for access token
    """
    from fastapi import Form
    
    # Parse form data if Content-Type is application/x-www-form-urlencoded
    content_type = request.headers.get("content-type", "")
    if "application/x-www-form-urlencoded" in content_type:
        form_data = await request.form()
        grant_type = form_data.get("grant_type") or grant_type
        code = form_data.get("code") or code
        redirect_uri = form_data.get("redirect_uri") or redirect_uri
        client_id = form_data.get("client_id") or client_id
        code_verifier = form_data.get("code_verifier") or code_verifier
        scope = form_data.get("scope") or scope
    
    from urllib.parse import unquote
    
    # Decode URL-encoded client_id if needed
    if client_id:
        client_id = unquote(client_id)
    
    expected_key = os.getenv("MCP_API_KEY")
    
    # Simplified OAuth: If grant_type is authorization_code, return access token
    if grant_type == "authorization_code":
        # For simplified flow, accept any valid code and return API key as access token
        # In production, verify code against stored codes
        if code and client_id:
            # Return access token (use API key as token)
            # Claude.ai will use this as Bearer token for subsequent requests
            access_token = expected_key
            return {
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": scope or "claudeai",
            }
        else:
            return JSONResponse(
                content={"error": "invalid_request", "error_description": "Missing code or client_id"},
                status_code=400,
            )
    
    # Client credentials grant (for direct API access)
    elif grant_type == "client_credentials":
        # If client_id is the API key, return it as access token
        if client_id == expected_key or (client_id and len(client_id) == 64):
            access_token = expected_key
            return {
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": 3600,
            }
        # If client_id is connector name, use API key as token
        elif client_id:
            access_token = expected_key
            return {
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": 3600,
            }
    
    return JSONResponse(
        content={"error": "unsupported_grant_type", "error_description": f"Grant type {grant_type} not supported"},
        status_code=400,
    )


@app.get("/")
async def root():
    return {
        "name": "Obsidian MCP Server",
        "version": "1.0.0",
        "endpoints": {
            "mcp": "/mcp",
            "health": "/health",
            "oauth_authorize": "/authorize",
            "oauth_token": "/token",
        },
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


# Removed: handle_jsonrpc_method function - using mcp_handler.handle_request instead


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


@app.get("/mcp/debug")
async def debug_endpoint():
    return {
        "status": "Server is running",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tools_count": len(mcp_handler.tools),
        "server_info": mcp_handler.server_info,
    }


@app.post("/mcp")
async def mcp_endpoint(request: Request, api_key: str = Depends(verify_api_key)):
    """
    MCP Streamable HTTP endpoint with SSE support
    Accepts JSON-RPC 2.0 requests and returns appropriate responses
    Supports both single JSON responses and Server-Sent Events streaming
    """
    try:
        # Parse request body and log for debugging
        body = await request.body()
        print(
            f"📥 MCP Request from {request.client.host if request.client else 'unknown'}"
        )
        print(f"📋 Headers: {dict(request.headers)}")
        print(f"📄 Body: {body.decode()}")
        try:
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
