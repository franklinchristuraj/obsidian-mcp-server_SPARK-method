# Product Requirements Document
## Remote HTTPS Streamable MCP Server for Obsidian Vault

### 1. Overview

**Product Name**: Obsidian MCP Server  
**Version**: 1.0  
**Purpose**: Enable remote access to Obsidian vault through Model Context Protocol (MCP) via HTTPS, allowing AI assistants to interact with notes programmatically.

---

### 2. Objectives

- Provide full vault access (read/write) through MCP protocol
- Expose both MCP Tools (actions) and Resources (browsing)
- Enable remote access via HTTPS with simple token authentication
- Support streaming responses for efficient data transfer
- Deploy on VPS for 24/7 availability

---

### 3. Technical Architecture

#### 3.1 Tech Stack

- **Language**: Python 3.10+
- **Web Framework**: FastAPI
- **MCP Implementation**: `mcp` Python package
- **Obsidian Integration**: Local REST API plugin
- **Deployment**: VPS (Ubuntu/Debian recommended)
- **Process Manager**: systemd or supervisor

#### 3.2 System Components

```
┌─────────────────┐
│   MCP Client    │
│  (Claude/AI)    │
└────────┬────────┘
         │ HTTPS
         ▼
┌─────────────────┐
│  FastAPI Server │
│  (MCP Protocol) │
└────────┬────────┘
         │ HTTP
         ▼
┌─────────────────┐
│ Obsidian Vault  │
│  + REST API     │
└─────────────────┘
```

---

### 4. Functional Requirements

#### 4.1 MCP Resources (Read Access)

**Resource URI Pattern**: `obsidian://notes/{path}`

| Resource | Description | URI Example |
|----------|-------------|-------------|
| Vault Root | List all notes in vault | `obsidian://notes/` |
| Specific Note | Access individual note content | `obsidian://notes/daily/2024-01-15.md` |
| Folder Contents | List notes in specific folder | `obsidian://notes/projects/` |

**Response Format**:
- MIME Type: `text/markdown` for note content
- MIME Type: `application/json` for listings

#### 4.2 MCP Tools (Actions)

| Tool Name | Description | Parameters |
|-----------|-------------|------------|
| `search_notes` | Search vault using query | `query` (string, required)<br>`folder` (string, optional) |
| `read_note` | Read specific note content | `path` (string, required) |
| `create_note` | Create new note | `path` (string, required)<br>`content` (string, required) |
| `update_note` | Update existing note | `path` (string, required)<br>`content` (string, required) |
| `append_note` | Append to existing note | `path` (string, required)<br>`content` (string, required) |
| `delete_note` | Delete note | `path` (string, required) |
| `list_notes` | List notes in folder | `folder` (string, optional) |
| `get_vault_structure` | Get folder tree | None |
| `execute_command` | Run Obsidian command | `command` (string, required) |

#### 4.3 Core Operations

**Search**:
- Full-text search across vault
- Optional folder filtering
- Return matching note paths and snippets

**Read**:
- Fetch complete note content
- Support for nested folders
- Handle special characters in paths

**Write Operations**:
- Create notes with frontmatter support
- Update entire note content
- Append content preserving existing text
- Auto-create parent folders if needed

**List/Browse**:
- Recursive folder listing
- Return metadata (modified date, size)
- Support filtering by extension

**Commands**:
- Execute Obsidian commands via REST API
- Support common commands (open note, create link, etc.)

---

### 5. API Specifications

#### 5.1 MCP Endpoint

**Base URL**: `https://your-vps-domain.com/mcp`

**Protocol**: Server-Sent Events (SSE) for streaming

**Authentication**: 
- Header: `Authorization: Bearer <API_KEY>`
- Environment variable: `MCP_API_KEY`

#### 5.2 Request/Response Flow

```json
// Tool Execution Request
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "search_notes",
    "arguments": {
      "query": "machine learning",
      "folder": "research"
    }
  }
}

// Streaming Response
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Found 3 notes:\n1. research/ml-basics.md\n2. research/neural-networks.md\n..."
      }
    ]
  }
}
```

---

### 6. Configuration

#### 6.1 Environment Variables

```bash
# Server Configuration
MCP_HOST=0.0.0.0
MCP_PORT=8888
MCP_API_KEY=your-secret-token-here

# Obsidian REST API Configuration (VERIFIED)
OBSIDIAN_API_URL=http://148.230.124.28:4443
OBSIDIAN_API_KEY=YOUR_OBSIDIAN_API_KEY
OBSIDIAN_VAULT_PATH=/root/obsidian/franklin-vault

# Optional
MCP_LOG_LEVEL=INFO
MCP_ENABLE_CORS=true
```

#### 6.2 Configuration File (config.yaml)

```yaml
server:
  host: 0.0.0.0
  port: 8000
  base_path: /mcp
  
obsidian:
  api_url: http://localhost:27123
  vault_path: /home/user/ObsidianVault
  
security:
  api_key_header: Authorization
  require_auth: true
  
features:
  enable_streaming: true
  max_search_results: 50
  cache_ttl: 300
```

---

### 7. Implementation Phases

#### Phase 1: Core MCP Server (Week 1)
- [ ] Set up FastAPI project structure
- [ ] Implement MCP protocol handler
- [ ] Create SSE streaming endpoint
- [ ] Add API key authentication middleware
- [ ] Basic health check endpoint

#### Phase 2: Obsidian Integration (Week 1)
- [ ] Implement Obsidian REST API client wrapper
- [ ] Create note CRUD operations
- [ ] Implement search functionality
- [ ] Add folder/vault structure traversal
- [ ] Error handling and validation

#### Phase 3: MCP Tools (Week 2)
- [ ] Implement all 9 MCP tools
- [ ] Add input validation and sanitization
- [ ] Create tool response formatting
- [ ] Add streaming support for large responses
- [ ] Tool usage documentation

#### Phase 4: MCP Resources (Week 2)
- [ ] Implement resource URI routing
- [ ] Add resource listing capabilities
- [ ] Support for different content types
- [ ] Resource metadata handling
- [ ] Caching layer for frequently accessed resources

#### Phase 5: Deployment (Week 3)
- [ ] VPS setup and configuration
- [ ] SSL/TLS certificate (Let's Encrypt)
- [ ] Nginx reverse proxy configuration
- [ ] systemd service setup
- [ ] Logging and monitoring
- [ ] Backup strategy for configurations

---

### 8. Security Considerations

**Note**: Security is deprioritized per requirements, but basic measures included:

- **Authentication**: Simple bearer token validation
- **HTTPS**: TLS encryption for data in transit
- **Input Validation**: Prevent path traversal attacks
- **Rate Limiting**: Optional basic rate limiting (not required)

**Explicitly Not Implemented**:
- User management
- OAuth/Advanced authentication
- Audit logging
- Data encryption at rest
- IP whitelisting

---

### 9. Testing Requirements

#### 9.1 Manual Testing

- Test each MCP tool with various inputs
- Verify streaming responses work correctly
- Test authentication (valid/invalid tokens)
- Verify Obsidian REST API integration
- Test error handling and edge cases

#### 9.2 Integration Testing

- End-to-end MCP client connection
- Large note handling (>1MB content)
- Concurrent request handling
- Network interruption recovery
- Obsidian vault changes sync

---

### 10. Deployment Guide

#### 10.1 VPS Requirements

- **OS**: Ubuntu 22.04 LTS or Debian 11+
- **RAM**: 1GB minimum (2GB recommended)
- **Storage**: 10GB minimum
- **Python**: 3.10+
- **Network**: Public IP with open port 443 (HTTPS)

#### 10.2 Deployment Steps

1. Clone repository to VPS
2. Install Python dependencies (`pip install -r requirements.txt`)
3. Configure environment variables
4. Set up Nginx as reverse proxy
5. Configure SSL with Certbot
6. Create systemd service
7. Start and enable service
8. Test MCP connection from client

#### 10.3 Example systemd Service

```ini
[Unit]
Description=Obsidian MCP Server
After=network.target

[Service]
Type=simple
User=obsidian
WorkingDirectory=/opt/obsidian-mcp
Environment="PATH=/opt/obsidian-mcp/venv/bin"
EnvironmentFile=/opt/obsidian-mcp/.env
ExecStart=/opt/obsidian-mcp/venv/bin/python main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

---

### 11. Success Criteria

- [ ] MCP client successfully connects via HTTPS
- [ ] All 9 tools execute correctly
- [ ] Resources browseable via URI pattern
- [ ] Streaming responses work for large content
- [ ] Authentication validates API keys
- [ ] Server runs continuously on VPS
- [ ] Response time < 2s for typical operations
- [ ] Can handle vault with 1000+ notes

---

### 12. Project Structure

```
obsidian-mcp-server/
├── main.py                 # FastAPI application entry
├── requirements.txt        # Python dependencies
├── config.yaml            # Configuration file
├── .env.example           # Environment template
├── README.md              # Setup instructions
├── src/
│   ├── __init__.py
│   ├── mcp_server.py      # MCP protocol implementation
│   ├── obsidian_client.py # Obsidian REST API wrapper
│   ├── tools/             # MCP tools implementation
│   │   ├── __init__.py
│   │   ├── search.py
│   │   ├── read.py
│   │   ├── write.py
│   │   └── vault.py
│   ├── resources/         # MCP resources implementation
│   │   ├── __init__.py
│   │   └── notes.py
│   ├── auth.py            # Authentication middleware
│   └── utils.py           # Shared utilities
├── deploy/
│   ├── nginx.conf         # Nginx configuration
│   ├── systemd.service    # systemd service file
│   └── setup.sh           # Deployment script
└── tests/
    └── manual_tests.md    # Manual testing checklist
```

---

### 13. Key Dependencies

```txt
fastapi==0.104.1
uvicorn[standard]==0.24.0
mcp==0.9.0
httpx==0.25.2
python-dotenv==1.0.0
pyyaml==6.0.1
pydantic==2.5.0
pydantic-settings==2.1.0
```

---

### 14. Future Enhancements (Out of Scope for v1.0)

- Webhook support for vault changes
- WebSocket alternative to SSE
- Multi-vault support
- Advanced search (regex, tags, metadata)
- Note templates
- Batch operations
- GraphQL API option
- Docker containerization
- Prometheus metrics

---

### 15. Documentation Deliverables

- [ ] API documentation (auto-generated from FastAPI)
- [ ] Setup guide for VPS deployment
- [ ] MCP client configuration examples
- [ ] Troubleshooting guide
- [ ] Architecture diagram
- [ ] Sample .env file with comments

---

### 16. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Obsidian REST API plugin breaking changes | High | Pin plugin version, monitor updates |
| VPS downtime | Medium | Use reliable VPS provider, monitoring |
| Large vault performance | Medium | Implement pagination, caching |
| API key exposure | Low | Use HTTPS, rotate keys periodically |

---

### End of PRD

**Next Steps**: 
1. Set up development environment
2. Initialize FastAPI project structure
3. Begin Phase 1 implementation with Cursor
4. Test basic MCP connectivity