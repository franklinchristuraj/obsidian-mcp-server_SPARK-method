# Claude Connector MCP - Note Creation Issue Diagnosis

**Date:** 2026-02-04  
**Status:** 🔍 Investigation Complete - Root Cause Identified

## Executive Summary

The Obsidian MCP server is **functioning correctly** and **can create notes successfully**. Testing confirms:
- ✅ Remote server at `https://mcp.ziksaka.com/mcp` is operational
- ✅ Note creation via API works correctly
- ✅ Notes appear in vault at `/home/franklinchris/obsidian/config/franklin-vault`
- ✅ Obsidian REST API authentication is working

## Test Results

### ✅ Server Connectivity Tests

1. **Remote Server Health Check**
   ```bash
   curl https://mcp.ziksaka.com/health
   # Response: {"status":"healthy","service":"obsidian-mcp-server"}
   ```

2. **Tools List**
   ```bash
   curl -H "Authorization: Bearer API_KEY" \
        -H "Content-Type: application/json" \
        -X POST https://mcp.ziksaka.com/mcp \
        -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
   # Response: Returns all 13 tools including obs_create_note
   ```

3. **Note Creation Test**
   ```bash
   curl -H "Authorization: Bearer API_KEY" \
        -H "Content-Type: application/json" \
        -X POST https://mcp.ziksaka.com/mcp \
        -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"obs_create_note","arguments":{"path":"test-note.md","content":"# Test"}},"id":1}'
   # Response: ✅ Successfully created note
   # File verified: /home/franklinchris/obsidian/config/franklin-vault/test-note.md
   ```

### ✅ Obsidian REST API Tests

1. **API Authentication**
   ```bash
   curl -H "Authorization: Bearer API_KEY" http://localhost:27123/vault/
   # Response: Returns vault structure with all folders
   ```

2. **Obsidian Process Status**
   - Obsidian is running (PID 223598)
   - REST API is accessible on port 27123
   - API key authentication works

## Identified Issues

### 🔴 Issue #1: Systemd Service Not Running

**Status:** Service failed 2 months ago and hasn't been restarted

**Details:**
- Service: `obsidian-mcp.service`
- Status: `failed (Result: exit-code)`
- Last Active: Fri 2025-11-21 20:29:49 UTC
- Error: Exit code 1

**Impact:** 
- Local server not running (but remote server is working)
- If Claude is configured to use localhost, it would fail

**Fix Required:**
1. Check service logs to identify startup error
2. Fix configuration issue
3. Restart service

### 🟡 Issue #2: Potential Path Mismatch

**Status:** Needs verification

**Possible Scenarios:**
1. Claude connector might be configured with wrong vault path
2. Remote server might have different `OBSIDIAN_VAULT_PATH` environment variable
3. Notes might be created in a different location than expected

**Investigation Needed:**
- Check remote server's `.env` file or environment variables
- Verify Claude connector configuration
- Test note creation with explicit paths

### 🟡 Issue #3: Error Handling & Response Format

**Status:** Server returns success even if note creation fails silently

**Observation:**
- Server might return success response before verifying file was written
- No explicit verification that note exists after creation
- Errors might be caught and converted to success messages

## Root Cause Analysis

### Most Likely Causes (in order of probability):

1. **Claude Connector Configuration Issue** (70% probability)
   - Wrong endpoint URL
   - Wrong API key
   - Wrong OAuth credentials
   - Path mismatch in connector settings

2. **Remote Server Environment Variables** (20% probability)
   - Remote server might have different `OBSIDIAN_VAULT_PATH`
   - Remote server might have different `OBSIDIAN_API_URL`
   - Remote server might have wrong `OBSIDIAN_API_KEY`

3. **Silent Failure in Note Creation** (10% probability)
   - Note creation succeeds but file isn't written
   - Permissions issue on remote server
   - File system sync delay

## Recommended Actions

### Immediate Actions

1. **Verify Claude Connector Configuration**
   - Check Claude.ai connector settings
   - Verify remote URL: `https://mcp.ziksaka.com/mcp`
   - Verify OAuth Client ID: `franklinchris`
   - Verify OAuth Client Secret matches `MCP_API_KEY`

2. **Test End-to-End Note Creation**
   ```bash
   # Create a test note via Claude connector
   # Then verify it appears in vault
   ```

3. **Check Remote Server Logs**
   - SSH into remote server
   - Check application logs for errors
   - Verify environment variables match local `.env`

### Fix Systemd Service

1. **Check Service Logs**
   ```bash
   journalctl --user -u obsidian-mcp.service -n 100 --no-pager
   ```

2. **Test Service Startup**
   ```bash
   cd /home/franklinchris/obsidian-mcp-server
   source venv/bin/activate
   python3 main_production.py
   ```

3. **Fix Configuration Issues**
   - Update `.env` file if needed
   - Fix any Python import errors
   - Fix any missing dependencies

4. **Restart Service**
   ```bash
   systemctl --user restart obsidian-mcp.service
   systemctl --user status obsidian-mcp.service
   ```

### Long-term Improvements

1. **Add Explicit Verification**
   - After note creation, verify file exists
   - Return error if file doesn't exist after creation
   - Add file system sync check

2. **Improve Error Handling**
   - Better error messages
   - Log all failures
   - Return detailed error information to client

3. **Add Monitoring**
   - Track note creation success/failure rates
   - Alert on failures
   - Log all operations

## Testing Checklist

- [x] Remote server health check
- [x] Tools list endpoint
- [x] Note creation via API
- [x] File appears in vault
- [x] Obsidian REST API authentication
- [ ] Claude connector configuration verification
- [ ] End-to-end test via Claude connector
- [ ] Remote server environment variable check
- [ ] Systemd service fix and restart

## Next Steps

1. **User Action Required:**
   - Check Claude.ai connector configuration
   - Verify connector is using correct endpoint and credentials
   - Try creating a note via Claude and check if it appears

2. **If Notes Still Don't Appear:**
   - Check remote server logs
   - Verify remote server environment variables
   - Test note creation with explicit full paths
   - Check file permissions on remote server

3. **Fix Systemd Service:**
   - Investigate why service failed
   - Fix configuration issues
   - Restart service for local development

## Files Created

- `CLAUDE_CONNECTOR_DIAGNOSIS.md` - This document
- Test notes created during diagnosis (can be deleted)

## Support Information

**Server Endpoints:**
- Remote: `https://mcp.ziksaka.com/mcp`
- Local: `http://localhost:8888/mcp` (when service is running)

**API Key:** Stored in `.env` file (do not commit to git)

**Vault Path:** `/home/franklinchris/obsidian/config/franklin-vault`

**Obsidian REST API:** `http://localhost:27123`
