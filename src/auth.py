"""
Authentication Middleware
"""
from fastapi import Header, HTTPException, status, Request
import os


async def verify_api_key(
    request: Request,
    authorization: str = Header(None),
) -> str:
    """Verify API key from Authorization header, query parameter, or OAuth Client ID header"""
    expected_key = os.getenv("MCP_API_KEY")
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
    
    # Method 2: Query parameter (for Claude.ai connectors)
    if not token:
        token = request.query_params.get("api_key") or request.query_params.get("client_id")
    
    # Method 3: OAuth Client ID header (for Claude.ai)
    if not token:
        token = request.headers.get("X-Client-ID") or request.headers.get("X-API-Key")
    
    # If no token found, raise error
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header, api_key query parameter, or X-Client-ID header",
        )

    # Verify token matches expected key
    if expected_key and token != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
        )

    return token
