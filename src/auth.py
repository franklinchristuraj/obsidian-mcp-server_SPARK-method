"""
Authentication Middleware
"""
from fastapi import Header, HTTPException, status
import os


async def verify_api_key(authorization: str = Header(None)) -> str:
    """Verify API key from Authorization header (optional for reverse proxy)"""
    expected_key = os.getenv("MCP_API_KEY")
    require_auth = os.getenv("MCP_REQUIRE_AUTH", "true").lower() == "true"

    # If authentication is disabled (for reverse proxy), skip verification
    if not require_auth:
        return "proxy-authenticated"

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    # Extract token from "Bearer <token>"
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise ValueError("Invalid authentication scheme")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format",
        )

    if expected_key and token != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
        )

    return token
