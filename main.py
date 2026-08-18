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
import uuid
from typing import Dict, Any, Optional, AsyncGenerator
from src.auth import verify_api_key
from src.scope import workspace_ctx
from src.mcp_server import mcp_handler, MCPProtocolHandler
from src.token_store import TokenStore, generate_token, verify_pkce
from src import observability
from src import request_context
from src.tasks import task_store
from src.request_context import (
    build_request_meta,
    name_from_params,
)
from src import cimd as cimd_mod
from src.cimd import CimdError, resolve_oauth_client

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
    await observability.init_observability()
    asyncio.create_task(observability.run_background_writer())
    await task_store.init_db()
    from src.tasks import run_task_poller

    asyncio.create_task(run_task_poller(task_store))


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
        # S256 only — plain is advertised nowhere (not implemented)
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        # SEP-991 Client ID Metadata Documents (CIMD); DCR remains via registration_endpoint
        "client_id_metadata_document_supported": True,
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
    Resolves client via CIMD (HTTPS URL client_id) or DCR.
    """
    from urllib.parse import unquote

    if response_type != "code":
        return JSONResponse(
            content={"error": "unsupported_response_type", "error_description": "Only response_type=code is supported"},
            status_code=400,
        )

    if client_id:
        client_id = unquote(client_id)

    if not client_id:
        return JSONResponse(
            content={"error": "invalid_request", "error_description": "Missing client_id"},
            status_code=400,
        )

    if code_challenge_method and code_challenge_method != "S256":
        return JSONResponse(
            content={
                "error": "invalid_request",
                "error_description": "Only code_challenge_method=S256 is supported",
            },
            status_code=400,
        )

    try:
        resolved = await resolve_oauth_client(
            client_id, get_dcr_client=token_store.get_client
        )
    except CimdError as e:
        return JSONResponse(
            content={"error": "invalid_client", "error_description": str(e)},
            status_code=400,
        )

    if resolved is None:
        # Unregistered opaque client_id — reject when redirect_uri present
        # (CIMD URLs that failed would have raised). Allow only with no redirect
        # for rare debug flows; production Claude always sends redirect_uri.
        if redirect_uri:
            return JSONResponse(
                content={
                    "error": "invalid_client",
                    "error_description": (
                        "Unknown client_id. Use a CIMD HTTPS URL or register via DCR."
                    ),
                },
                status_code=400,
            )
    elif redirect_uri:
        if redirect_uri not in resolved["redirect_uris"]:
            return JSONResponse(
                content={
                    "error": "invalid_request",
                    "error_description": "redirect_uri does not match client metadata",
                },
                status_code=400,
            )

    print(
        f"🔑 AUTHORIZE: client_id={client_id[:40]}... redirect_uri={redirect_uri} "
        f"source={(resolved or {}).get('source', 'none')}"
    )

    auth_code = generate_token()
    await token_store.store_auth_code(
        code=auth_code,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        scope=scope,
    )

    if redirect_uri:
        from urllib.parse import urlencode
        from fastapi.responses import RedirectResponse

        base_url = os.getenv("MCP_BASE_URL", "https://mcp.ziksaka.com")
        params = {"code": auth_code, "iss": base_url}
        if state:
            params["state"] = state
        separator = "&" if "?" in redirect_uri else "?"
        redirect_url = f"{redirect_uri}{separator}{urlencode(params)}"
        print(f"↩️  REDIRECT: {redirect_url[:100]}...")
        return RedirectResponse(url=redirect_url, status_code=302)

    return {"code": auth_code, "state": state, "iss": os.getenv("MCP_BASE_URL", "https://mcp.ziksaka.com")}


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

        # Bind token-request client_id to the code's client_id
        if client_id != code_data["client_id"]:
            return JSONResponse(
                content={
                    "error": "invalid_grant",
                    "error_description": "client_id does not match authorization code",
                },
                status_code=400,
            )

        # redirect_uri must match the one used at authorize (when both present)
        stored_redirect = code_data.get("redirect_uri")
        if stored_redirect and redirect_uri and str(redirect_uri) != stored_redirect:
            return JSONResponse(
                content={
                    "error": "invalid_grant",
                    "error_description": "redirect_uri does not match authorization request",
                },
                status_code=400,
            )

        # PKCE: required when challenge was stored
        if code_data.get("code_challenge"):
            if not code_verifier:
                return JSONResponse(
                    content={
                        "error": "invalid_grant",
                        "error_description": "Missing code_verifier for PKCE",
                    },
                    status_code=400,
                )
            if not verify_pkce(code_data["code_challenge"], str(code_verifier)):
                return JSONResponse(
                    content={"error": "invalid_grant", "error_description": "PKCE verification failed"},
                    status_code=400,
                )

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
    # SEP-2243: Mcp-Method / Mcp-Name disagree with JSON-RPC body
    "HEADER_MISMATCH": {"code": -32020, "message": "Header mismatch"},
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
    """Emit an MCP-compliant Streamable HTTP SSE response.

    MCP Streamable HTTP requires every SSE ``data:`` event to be a JSON-RPC
    message; the client reads the response(s) and treats the request as done
    when the stream closes. The prior implementation appended OpenAI-style
    ``{"type": "content"/"list_item"}`` chunks plus a ``data: [DONE]`` sentinel.
    Neither is valid JSON-RPC, and ``[DONE]`` is not even valid JSON, so
    spec-compliant clients abort mid-stream with
    ``Unexpected token 'D', "[DONE]" is not valid JSON``. The complete response
    already rides in the single event below, so the chunks were redundant. Emit
    exactly one response event and close.

    ``result_data`` / ``enable_streaming`` are kept for call-site compatibility
    but intentionally unused.
    """
    yield f"data: {json.dumps(jsonrpc_response)}\n\n"


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
    Legacy MCP Streamable HTTP GET endpoint (SSE keepalive).

    Kept for older hosts that open a long-lived GET channel. Modern
    2026-07-28 clients should not depend on this; prefer opt-in
    subscriptions/listen when that is implemented.
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


def _header_safe(value: str) -> str:
    """Coerce a string to something usable as an HTTP header value.

    Header values are latin-1 encoded, so any character outside that range
    raises when the response is built rather than at the call site.
    """
    try:
        value.encode("latin-1")
    except UnicodeEncodeError:
        return value.encode("ascii", "backslashreplace").decode("ascii")
    return value


def _log_tools_call(
    session_id: str,
    client: str,
    params: Optional[Dict[str, Any]],
    result: Any,
    start: float,
    status: str,
    error: Optional[str],
) -> None:
    """Best-effort tool-call logging around the tools/call boundary. Never
    raises — wraps observability.log_tool_call, which itself never raises,
    plus the result-inspection logic that can (e.g. non-serializable data)."""
    try:
        tool_name = (params or {}).get("name", "unknown")
        args = (params or {}).get("arguments", {}) or {}
        if isinstance(result, dict) and result.get("isError"):
            status = "error"
            if error is None:
                content = result.get("content") or []
                if content and isinstance(content[0], dict):
                    error = content[0].get("text")
        try:
            response_bytes = len(json.dumps(result, default=str).encode("utf-8"))
        except Exception:
            response_bytes = 0
        observability.log_tool_call(
            session_id=session_id,
            client=client,
            tool_name=tool_name,
            args=args,
            status=status,
            error=error,
            latency_ms=int((time.monotonic() - start) * 1000),
            response_bytes=response_bytes,
        )
    except Exception:
        pass


def _validate_mcp_headers(
    request: Request,
    method: str,
    params: Optional[Dict[str, Any]],
    is_modern: bool,
    request_id: Optional[Any],
) -> Optional[Dict[str, Any]]:
    """Validate Mcp-Method / Mcp-Name against the JSON-RPC body (SEP-2243)."""
    mcp_method = request.headers.get("mcp-method")
    mcp_name = request.headers.get("mcp-name")

    if is_modern and not mcp_method:
        return create_jsonrpc_error(
            "HEADER_MISMATCH",
            "Mcp-Method header required for protocol 2026-07-28",
            request_id,
        )

    if mcp_method is not None and mcp_method != method:
        return create_jsonrpc_error(
            "HEADER_MISMATCH",
            f"Mcp-Method={mcp_method!r} does not match body method={method!r}",
            request_id,
        )

    needs_name = method in ("tools/call", "prompts/get", "resources/read")
    body_name = name_from_params(method, params)

    if needs_name:
        if is_modern and not mcp_name:
            return create_jsonrpc_error(
                "HEADER_MISMATCH",
                f"Mcp-Name header required for {method}",
                request_id,
            )
        if mcp_name is not None and body_name is not None and mcp_name != body_name:
            return create_jsonrpc_error(
                "HEADER_MISMATCH",
                f"Mcp-Name={mcp_name!r} does not match body name={body_name!r}",
                request_id,
            )
    return None


@app.post("/mcp")
async def mcp_endpoint(request: Request, auth=Depends(verify_api_key)):
    """
    MCP Streamable HTTP endpoint with SSE support.

    Dual-compat: legacy initialize + Mcp-Session-Id clients, and
    2026-07-28 stateless requests with _meta + Mcp-Method/Mcp-Name headers.
    """
    try:
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

        validation_error = validate_jsonrpc_request(request_data)
        if validation_error:
            return JSONResponse(content=validation_error, status_code=400)

        request_id = request_data.get("id")
        method = request_data["method"]
        params = request_data.get("params")

        accept_header = request.headers.get("accept", "")
        wants_streaming = "text/event-stream" in accept_header

        header_protocol = request.headers.get("mcp-protocol-version")
        req_meta = build_request_meta(
            params=params if isinstance(params, dict) else None,
            header_protocol_version=header_protocol,
        )

        header_err = _validate_mcp_headers(
            request,
            method,
            params if isinstance(params, dict) else None,
            req_meta.is_modern,
            request_id,
        )
        if header_err:
            return JSONResponse(content=header_err, status_code=400)

        incoming_session_id = request.headers.get("mcp-session-id")
        correlation_id = observability.resolve_correlation_id(
            incoming_session_id=incoming_session_id,
            identity=auth.identity,
            method=method,
            is_modern=req_meta.is_modern,
        )
        correlation_id = _header_safe(correlation_id)

        client_name = (req_meta.client_info or {}).get("name")
        if client_name:
            obs_client = observability.classify_client_from_info(str(client_name))
        else:
            obs_client = observability.resolve_client(correlation_id)

        resp_headers = {"Mcp-Session-Id": correlation_id}

        ctx_token = workspace_ctx.set(auth)
        obs_token = observability.call_context.set(
            observability.CallContext(session_id=correlation_id, client=obs_client)
        )
        meta_token = request_context.request_meta.set(req_meta)
        tool_call_start = time.monotonic()
        try:
            result = await mcp_handler.handle_request(method, params)

            if method == "initialize" and isinstance(params, dict):
                client_info = params.get("clientInfo") or {}
                observability.register_session_client(
                    correlation_id, client_info.get("name")
                )

            if method == "tools/call":
                _log_tools_call(
                    correlation_id, obs_client, params, result, tool_call_start,
                    status="ok", error=None,
                )

            if method.startswith("notifications/") and result is None:
                return Response(status_code=202, headers=resp_headers)

            response = create_jsonrpc_response(result=result, request_id=request_id)
            should_stream = wants_streaming and _should_enable_streaming(result)

            if should_stream:
                return StreamingResponse(
                    create_sse_stream(response, result, enable_streaming=True),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Headers": (
                            "Content-Type, Authorization, "
                            "Mcp-Session-Id, Mcp-Protocol-Version, Mcp-Method, Mcp-Name"
                        ),
                        **resp_headers,
                    },
                )
            return JSONResponse(content=response, headers=resp_headers)

        except ValueError as e:
            if method == "tools/call":
                _log_tools_call(
                    correlation_id, obs_client, params, None, tool_call_start,
                    status="error", error=str(e),
                )
            return JSONResponse(
                content=create_jsonrpc_error("METHOD_NOT_FOUND", str(e), request_id),
                status_code=404,
                headers=resp_headers,
            )
        except Exception as e:
            if method == "tools/call":
                _log_tools_call(
                    correlation_id, obs_client, params, None, tool_call_start,
                    status="error", error=str(e),
                )
            return JSONResponse(
                content=create_jsonrpc_error("INTERNAL_ERROR", str(e), request_id),
                status_code=500,
                headers=resp_headers,
            )
        finally:
            workspace_ctx.reset(ctx_token)
            observability.call_context.reset(obs_token)
            request_context.request_meta.reset(meta_token)

    except Exception as e:
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
