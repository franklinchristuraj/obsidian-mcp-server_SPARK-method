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
from typing import Dict, Any, Optional, AsyncGenerator
from src.auth import verify_api_key
from src.scope import workspace_ctx
from src.mcp_server import mcp_handler, MCPProtocolHandler
from src.token_store import TokenStore, generate_token, verify_pkce

# Load environment variables
load_dotenv()

# Token store (initialized at startup)
token_store = TokenStore(db_path=os.getenv("TOKEN_DB_PATH", "tokens.db"))

# Create FastAPI app
app = FastAPI(
    title="Obsidian MCP Server",
    description="Model Context Protocol server for Obsidian vault",
    version="1.0.0",
)


@app.on_event("startup")
async def startup():
    await token_store.init_db()
    asyncio.create_task(_periodic_cleanup())


async def _periodic_cleanup():
    """Delete expired tokens every hour."""
    while True:
        await asyncio.sleep(3600)
        await token_store.cleanup_expired()


from fastapi.exceptions import HTTPException as FastAPIHTTPException

@app.exception_handler(FastAPIHTTPException)
async def http_exception_handler(request: Request, exc: FastAPIHTTPException):
    """
    Override FastAPI's default HTTPException handler so that 401 responses
    include the WWW-Authenticate header required for MCP OAuth discovery.
    """
    if exc.status_code == 401:
        base_url = os.getenv("MCP_BASE_URL", "https://mcp.ziksaka.com")
        resource_metadata_url = f"{base_url}/.well-known/oauth-protected-resource"
        return JSONResponse(
            status_code=401,
            content={"detail": exc.detail if hasattr(exc, "detail") else "Unauthorized"},
            headers={
                "WWW-Authenticate": f'Bearer resource_metadata="{resource_metadata_url}"',
            },
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "obsidian-mcp-server"}


@app.get("/.well-known/oauth-authorization-server")
async def oauth_server_metadata():
    """OAuth 2.0 Authorization Server Metadata (RFC 8414). Required for MCP discovery."""
    base_url = os.getenv("MCP_BASE_URL", "https://mcp.ziksaka.com")
    return {
        "issuer": base_url,
        "authorization_endpoint": f"{base_url}/authorize",
        "token_endpoint": f"{base_url}/token",
        "registration_endpoint": f"{base_url}/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256", "plain"],
        "token_endpoint_auth_methods_supported": ["none"],
    }


@app.get("/.well-known/oauth-protected-resource")
async def oauth_protected_resource_metadata():
    """OAuth 2.0 Protected Resource Metadata (RFC 9728). Required for MCP discovery."""
    base_url = os.getenv("MCP_BASE_URL", "https://mcp.ziksaka.com")
    return {
        "resource": f"{base_url}/mcp",
        "authorization_servers": [base_url],
        "scopes_supported": ["mcp"],
        "bearer_methods_supported": ["header"],
    }


@app.post("/register")
async def oauth_register(request: Request):
    """
    OAuth 2.0 Dynamic Client Registration (RFC 7591).
    Claude.ai POSTs here to register itself as an OAuth client before starting the auth flow.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            content={"error": "invalid_request", "error_description": "Request body must be JSON"},
            status_code=400,
        )

    client_name = body.get("client_name", "Unknown MCP Client")
    redirect_uris = body.get("redirect_uris", [])
    grant_types = body.get("grant_types", ["authorization_code", "refresh_token"])
    response_types = body.get("response_types", ["code"])
    token_endpoint_auth_method = body.get("token_endpoint_auth_method", "none")

    if not redirect_uris or not isinstance(redirect_uris, list):
        return JSONResponse(
            content={"error": "invalid_request", "error_description": "redirect_uris is required and must be a non-empty array"},
            status_code=400,
        )

    client = await token_store.register_client(
        client_name=client_name,
        redirect_uris=redirect_uris,
        grant_types=grant_types,
        response_types=response_types,
        token_endpoint_auth_method=token_endpoint_auth_method,
    )

    print(f"📝 DCR: Registered client '{client_name}' -> {client['client_id'][:20]}... redirect_uris={redirect_uris}")

    return JSONResponse(
        content={
            "client_id": client["client_id"],
            "client_name": client["client_name"],
            "redirect_uris": client["redirect_uris"],
            "grant_types": client["grant_types"],
            "response_types": client["response_types"],
            "token_endpoint_auth_method": client["token_endpoint_auth_method"],
        },
        status_code=201,
    )


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
    OAuth 2.0 Authorization endpoint (Authorization Code flow with PKCE).
    Generates a stored, single-use authorization code.
    """
    from urllib.parse import unquote

    if response_type != "code":
        return JSONResponse(
            content={"error": "unsupported_response_type", "error_description": "Only response_type=code is supported"},
            status_code=400,
        )

    # Decode URL-encoded client_id (Claude.ai may send "Obsidian+MCP+Server")
    if client_id:
        client_id = unquote(client_id)

    if not client_id:
        return JSONResponse(
            content={"error": "invalid_request", "error_description": "Missing client_id"},
            status_code=400,
        )

    # Validate that the client_id is registered (via DCR) or accept it as-is for flexibility
    registered_client = await token_store.get_client(client_id)
    if registered_client and redirect_uri:
        if redirect_uri not in registered_client["redirect_uris"]:
            return JSONResponse(
                content={"error": "invalid_request", "error_description": "redirect_uri does not match registered URIs"},
                status_code=400,
            )

    print(f"🔑 AUTHORIZE: client_id={client_id[:20]}... redirect_uri={redirect_uri} registered={'yes' if registered_client else 'no'}")

    # Generate and store a cryptographically random auth code
    auth_code = generate_token()
    await token_store.store_auth_code(
        code=auth_code,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        scope=scope,
    )

    if redirect_uri:
        from urllib.parse import urlencode, urlparse, parse_qs, urlunparse
        params = {"code": auth_code}
        if state:
            params["state"] = state
        # Use standard HTTP 302 redirect — this is what OAuth clients expect
        separator = "&" if "?" in redirect_uri else "?"
        redirect_url = f"{redirect_uri}{separator}{urlencode(params)}"
        from fastapi.responses import RedirectResponse
        print(f"↩️  REDIRECT: {redirect_url[:100]}...")
        return RedirectResponse(url=redirect_url, status_code=302)

    return {"code": auth_code, "state": state}


@app.post("/token")
async def oauth_token(request: Request):
    """
    OAuth 2.0 Token endpoint.
    Supports grant_type: authorization_code, refresh_token.
    """
    from urllib.parse import unquote

    # Always parse as form data (OAuth spec requires application/x-www-form-urlencoded)
    form_data = await request.form()
    grant_type = form_data.get("grant_type")
    code = form_data.get("code")
    redirect_uri = form_data.get("redirect_uri")
    client_id = form_data.get("client_id")
    code_verifier = form_data.get("code_verifier")
    refresh_token = form_data.get("refresh_token")
    scope = form_data.get("scope")

    if client_id:
        client_id = unquote(str(client_id))

    # ------------------------------------------------------------------
    # Grant: authorization_code
    # ------------------------------------------------------------------
    if grant_type == "authorization_code":
        if not code or not client_id:
            return JSONResponse(
                content={"error": "invalid_request", "error_description": "Missing code or client_id"},
                status_code=400,
            )

        code_data = await token_store.get_auth_code(str(code))
        if code_data is None:
            return JSONResponse(
                content={"error": "invalid_grant", "error_description": "Authorization code invalid or expired"},
                status_code=400,
            )

        # PKCE verification (S256 or plain)
        if code_data.get("code_challenge") and code_verifier:
            if not verify_pkce(code_data["code_challenge"], str(code_verifier)):
                return JSONResponse(
                    content={"error": "invalid_grant", "error_description": "PKCE verification failed"},
                    status_code=400,
                )

        # Consume the code (single-use)
        await token_store.delete_auth_code(str(code))

        access_token = generate_token()
        new_refresh = generate_token()
        effective_scope = scope or code_data.get("scope") or "mcp"
        await token_store.store_tokens(
            access_token=access_token,
            refresh_token=new_refresh,
            client_id=code_data["client_id"],
            scope=effective_scope,
        )

        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": new_refresh,
            "scope": effective_scope,
        }

    # ------------------------------------------------------------------
    # Grant: refresh_token  ← THIS is what fixes mobile persistence
    # ------------------------------------------------------------------
    elif grant_type == "refresh_token":
        if not refresh_token:
            return JSONResponse(
                content={"error": "invalid_request", "error_description": "Missing refresh_token"},
                status_code=400,
            )

        try:
            new_access, new_refresh = await token_store.rotate_refresh_token(str(refresh_token))
        except ValueError:
            return JSONResponse(
                content={"error": "invalid_grant", "error_description": "Refresh token invalid or expired"},
                status_code=400,
            )

        return {
            "access_token": new_access,
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": new_refresh,
            "scope": scope or "mcp",
        }

    return JSONResponse(
        content={"error": "unsupported_grant_type", "error_description": f"Grant type '{grant_type}' not supported"},
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
            "oauth_discovery": "/.well-known/oauth-authorization-server",
            "resource_metadata": "/.well-known/oauth-protected-resource",
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


@app.get("/mcp")
async def mcp_sse_endpoint(request: Request, _auth=Depends(verify_api_key)):
    """
    MCP Streamable HTTP GET endpoint (SSE channel).
    Required by the MCP spec for server-to-client event streaming.
    Keeps the connection open and sends a heartbeat so the client knows it's alive.
    """
    async def event_stream():
        # Send an initial endpoint event so Claude.ai knows the SSE channel is up
        yield "event: endpoint\ndata: /mcp\n\n"
        # Keep-alive heartbeats every 15 seconds
        while True:
            await asyncio.sleep(15)
            yield ": keepalive\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        },
    )


@app.post("/mcp")
async def mcp_endpoint(request: Request, auth=Depends(verify_api_key)):
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

        ctx_token = workspace_ctx.set(auth)
        try:
            # Use the new MCP protocol handler (tools read workspace_ctx)
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
        finally:
            workspace_ctx.reset(ctx_token)

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
