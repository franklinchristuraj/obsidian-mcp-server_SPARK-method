# Obsidian REST API Setup Guide

## Current Status
✅ **Obsidian REST API is fully functional**

**Verified Configuration (September 23, 2025)**:
- Service running on port 4443 at `http://148.230.124.28:4443`
- Local REST API plugin v3.2.0 installed and configured
- API key authentication working: `423a772ed267add25363e0f8bd9d15c71546598e07a69a9779cbde89b219deee`
- Vault path: `/root/obsidian/franklin-vault`
- All CRUD operations (Create, Read, Update, Delete) verified
- Vault structure accessible with SPARK methodology organization

## Required Setup Steps

### 1. Install Obsidian Desktop Application
Download and install Obsidian from https://obsidian.md/

### 2. Install REST API Plugin
1. Open Obsidian
2. Go to Settings → Community Plugins
3. Turn off Safe Mode if enabled
4. Browse and install "REST API" plugin
5. Enable the plugin

### 3. Configure REST API Plugin
1. Go to Settings → Community Plugins → REST API
2. Set API Port (currently configured: 36961, default: 27123)
3. Enable CORS if needed
4. Generate/set API key for security

### 4. Set Environment Variables
Create `.env` file in project root:
```bash
OBSIDIAN_API_URL=http://148.230.124.28:4443
OBSIDIAN_API_KEY=423a772ed267add25363e0f8bd9d15c71546598e07a69a9779cbde89b219deee
OBSIDIAN_VAULT_PATH=/root/obsidian/franklin-vault
```

### 5. Test Connection
Run the test script:
```bash
python3 test_obsidian_client.py
```

## Verified Vault Structure

The franklin-vault is organized using the SPARK methodology:

```
franklin-vault/
├── 00_system/           # System templates and utilities
├── 01_seeds/           # Raw idea capture (Digital Idea Inbox)
├── 02_projects/        # Active projects
├── 03_areas/           # Ongoing responsibilities
├── 04_resources/       # Reference materials
├── 05_knowledge/       # Processed insights
├── 06_daily-notes/     # Daily entries
└── 11_work-meeting-notes/ # Meeting records
```

### Vault Access Verification

**✅ Tested Operations:**
- ✅ Vault root listing: `GET /vault/`
- ✅ Folder navigation: `GET /vault/01_seeds/`
- ✅ Note reading: `GET /vault/01_seeds/_README.md`
- ✅ Note creation: `PUT /vault/Test/new-note.md`
- ✅ Note updating: `PUT /vault/Test/existing-note.md`
- ✅ Note deletion: `DELETE /vault/Test/test-note.md`

**📊 Test Results:**
- Health check: ✅ PASS
- Authentication: ✅ PASS
- CRUD operations: ✅ PASS
- Folder traversal: ✅ PASS
- Content verification: ✅ PASS

## Alternative: Mock Server for Development

If you want to test the MCP server without Obsidian:

```bash
# Create a simple mock server
python -m http.server 4443 --bind 0.0.0.0
```

## Troubleshooting

### Common Issues:
1. **Plugin not installed**: Install REST API plugin from Community Plugins
2. **Wrong port**: Check plugin settings for correct port
3. **API key mismatch**: Verify environment variable matches plugin setting
4. **CORS issues**: Enable CORS in plugin settings
5. **Firewall**: Ensure localhost connections are allowed

### Testing Commands:
```bash
# Check if Obsidian API is running
curl http://148.230.124.28:4443/

# Test with API key
curl -H "Authorization: Bearer 423a772ed267add25363e0f8bd9d15c71546598e07a69a9779cbde89b219deee" http://148.230.124.28:4443/vault/

# Test reading a specific note
curl -H "Authorization: Bearer 423a772ed267add25363e0f8bd9d15c71546598e07a69a9779cbde89b219deee" "http://148.230.124.28:4443/vault/01_seeds/_README.md"
```
