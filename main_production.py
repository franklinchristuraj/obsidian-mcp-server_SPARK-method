#!/usr/bin/env python3
"""
Obsidian MCP Server - Production Entry Point
"""
import sys
import uvicorn
import os
from dotenv import load_dotenv

# Load production environment (fallback to .env if .env.production doesn't exist).
# load_dotenv does not override already-set vars, so .env.production wins over
# .env, which in turn loses to anything already exported in the environment.
load_dotenv(".env.production")
load_dotenv(".env")  # Fallback to .env


def resolve_port() -> int:
    """Return the port to bind, or exit loudly if it is not configured.

    There is deliberately no default. A silent fallback binds a port nobody
    else expects: scripts/watchdog.sh then health-checks the configured port,
    sees no listener, and restart-loops a perfectly healthy server once a
    minute, while nginx proxies to a dead address. Failing at startup surfaces
    the missing config immediately instead of as a restart loop.
    """
    raw = os.getenv("MCP_PORT")
    if raw is None or not raw.strip():
        sys.exit(
            "FATAL: MCP_PORT is not set.\n"
            "  Set it in .env.production (preferred for prod), .env, or the "
            "environment.\n"
            "  See .env.example for the expected format (MCP_PORT=8000)."
        )
    try:
        port = int(raw.strip())
    except ValueError:
        sys.exit(f"FATAL: MCP_PORT must be an integer, got {raw.strip()!r}.")
    if not 1 <= port <= 65535:
        sys.exit(f"FATAL: MCP_PORT must be within 1-65535, got {port}.")
    return port


if __name__ == "__main__":
    # Production configuration
    uvicorn.run(
        "main:app",
        host=os.getenv("MCP_HOST", "127.0.0.1"),
        port=resolve_port(),
        workers=1,  # Single worker for now
        log_level=os.getenv("MCP_LOG_LEVEL", "info").lower(),
        access_log=True,
        reload=False,  # Disabled for production
    )
