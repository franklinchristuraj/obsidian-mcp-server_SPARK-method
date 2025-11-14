#!/usr/bin/env python3
"""
Obsidian MCP Server - Production Entry Point
"""
import uvicorn
import os
from dotenv import load_dotenv

# Load production environment (fallback to .env if .env.production doesn't exist)
load_dotenv(".env.production")
load_dotenv(".env")  # Fallback to .env

if __name__ == "__main__":
    # Production configuration
    uvicorn.run(
        "main:app",
        host=os.getenv("MCP_HOST", "127.0.0.1"),
        port=int(os.getenv("MCP_PORT", 8888)),
        workers=1,  # Single worker for now
        log_level=os.getenv("MCP_LOG_LEVEL", "info").lower(),
        access_log=True,
        reload=False,  # Disabled for production
    )
