"""
Authentication Middleware
"""
from fastapi import Header, HTTPException, status, Request
import os


async def verify_api_key(
    request: Request,
    authorization: str = Header(None),
) -> str:
    """Verify API key from Authorization header, query parameter, or OAuth Client ID/Secret"""
    expected_key = os.getenv("MCP_API_KEY")
    expected_client_id = os.getenv("MCP_CLIENT_ID", "franklinchris")
    require_auth = os.getenv("MCP_REQUIRE_AUTH", "true").lower() == "true"

    # If authentication is disabled (for reverse proxy), skip verification
    if not require_auth:
        return "proxy-authenticated"

    # Try to get API key from multiple sources
    token = None
    
    # Method 1: Authorization header (Bearer token)
    if authorization:
        try:
            scheme, token = authorization.split()
            if scheme.lower() != "bearer":
                token = None  # Try other methods
        except ValueError:
            pass
    
    # Method 2: OAuth-style Client ID + Client Secret (for Claude.ai connectors)
    client_id = (
        request.query_params.get("client_id")
        or request.headers.get("X-Client-ID")
    )
    client_secret = (
        request.query_params.get("client_secret")
        or request.headers.get("X-Client-Secret")
    )
    
    # If both client_id and client_secret are provided, validate OAuth-style
    if client_id and client_secret:
        # Validate client_secret matches API key
        if expected_key and client_secret == expected_key:
            return client_secret
        # If OAuth credentials provided but invalid, don't fall back to other methods
        # (security: reject invalid OAuth attempts immediately)
        if expected_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid OAuth client_secret"
            )
    
    # Method 3: Direct API key (backward compatibility)
    if not token:
        token = (
            request.query_params.get("api_key")
            or request.headers.get("X-API-Key")
        )
    
    # If no token found, raise error
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header, api_key query parameter, or OAuth client_id/client_secret",
        )

    # Verify token matches expected key
    if expected_key and token != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
        )

    return token
