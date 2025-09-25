#!/usr/bin/env python3
"""
Mock Obsidian REST API Server for Testing
Run this if you don't have Obsidian installed but want to test the MCP server
"""
import asyncio
import json
from fastapi import FastAPI, HTTPException, Header
from typing import Optional, List, Dict, Any
import uvicorn

app = FastAPI(title="Mock Obsidian REST API", version="1.0.0")

# Mock data
MOCK_VAULT_INFO = {
    "name": "Test Vault",
    "path": "/mock/vault/path",
    "files": 42,
    "folders": 8
}

MOCK_NOTES = [
    {
        "path": "Daily Notes/2024-01-01.md",
        "name": "2024-01-01",
        "stat": {"mtime": 1672531200000, "size": 150}
    },
    {
        "path": "Projects/Test Project.md", 
        "name": "Test Project",
        "stat": {"mtime": 1672531300000, "size": 250}
    },
    {
        "path": "Ideas/Random Thoughts.md",
        "name": "Random Thoughts", 
        "stat": {"mtime": 1672531400000, "size": 180}
    }
]

MOCK_NOTE_CONTENT = """# Test Note

This is a mock note for testing the Obsidian MCP Server.

## Features Tested
- [ ] Note reading
- [ ] Vault information
- [ ] Search functionality

## Links
[[Another Note]]
[[Daily Notes/2024-01-01]]

#testing #mock #obsidian
"""

@app.get("/")
async def root():
    return {"message": "Mock Obsidian REST API", "version": "1.0.0"}

@app.get("/vault/")
async def get_vault_info(authorization: Optional[str] = Header(None)):
    """Mock vault information endpoint"""
    if authorization:
        # Simple auth check - accept any Bearer token for testing
        if not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Invalid authorization format")
    
    return MOCK_VAULT_INFO

@app.get("/vault/{path:path}")
async def read_file(path: str, authorization: Optional[str] = Header(None)):
    """Mock file reading endpoint"""
    if authorization:
        if not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Invalid authorization format")
    
    # Return mock content for any file
    return MOCK_NOTE_CONTENT

@app.post("/search/simple/")
async def search_notes(query_data: Dict[str, str], authorization: Optional[str] = Header(None)):
    """Mock search endpoint"""
    if authorization:
        if not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Invalid authorization format")
    
    query = query_data.get("query", "")
    
    # Simple mock search - return notes that contain the query term
    results = []
    for note in MOCK_NOTES:
        if query.lower() in note["name"].lower() or query.lower() in note["path"].lower():
            results.append(note)
    
    return results

@app.get("/files/")
async def list_files(authorization: Optional[str] = Header(None)):
    """Mock file listing endpoint"""
    if authorization:
        if not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Invalid authorization format")
    
    return MOCK_NOTES

if __name__ == "__main__":
    print("🚀 Starting Mock Obsidian REST API Server")
    print("📍 Server will run on http://localhost:36961")
    print("🔑 Use any Bearer token for authentication")
    print("📝 Test endpoints:")
    print("   GET  /vault/           - Vault info")
    print("   GET  /vault/any-file   - Read note content") 
    print("   POST /search/simple/   - Search notes")
    print("   GET  /files/           - List files")
    print("\n💡 Set environment variable: OBSIDIAN_API_KEY=test-key")
    print("🛑 Press Ctrl+C to stop\n")
    
    uvicorn.run(app, host="127.0.0.1", port=36961, log_level="info")
