# Multi-Application MCP Server

A complete Model Context Protocol (MCP) server that provides AI assistants with full access to **Obsidian** vault operations, built with a scalable architecture designed for easy integration of additional productivity applications.

## 🎯 Project Status: **PRODUCTION READY**

### ✅ All Phases Complete
- **Phase 1**: Core MCP server with JSON-RPC 2.0 compliance ✅
- **Phase 2**: Enhanced Obsidian client with CRUD operations ✅  
- **Phase 3**: Complete MCP tools implementation (11 tools) ✅
- **Phase 4**: Dynamic MCP resources and vault browsing ✅
- **Phase 5**: Production deployment with template system ✅
- **Phase 6**: Multi-application architecture with extensible design ✅

### 🚀 Live Production Server
- **URL**: `https://mcp.ziksaka.com/mcp`
- **Status**: Active and serving requests
- **Authentication**: Bearer token required
- **SSL**: Let's Encrypt certificate

## 🏗️ Project Structure

```
📁 obsidian-mcp-server/
├── 📁 src/                    # Core application code
├── 📁 tests/                  # Test suite  
├── 📁 demos/                  # Example usage
├── 📁 docs/                   # All documentation (see docs/README.md)
│   ├── 📁 deployment/        # Deployment guides and configs
│   ├── 📁 claude/            # Claude Desktop integration
│   ├── 📁 guides/            # User guides
│   ├── 📁 phases/            # Development phase docs
│   └── 📁 setup/             # Setup guides
├── 📁 scripts/                # Utility scripts
├── main.py                    # Development server entry point
├── main_production.py         # Production server entry point
├── requirements.txt           # Python dependencies
├── config.yaml.example        # Configuration template
├── check_setup.py            # Setup verification script
└── README.md                  # This file
```

*See [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) for complete organization details.*

## 🌟 Key Features

### 🔧 MCP Tools (11 Total)

#### 📝 Obsidian Tools (obs_ prefix)
1. **obs_search_notes** - Advanced search with filters
2. **obs_read_note** - Read note content and metadata
3. **obs_create_note** - Create with automatic templates
4. **obs_update_note** - Format-preserving updates
5. **obs_append_note** - Add content safely
6. **obs_delete_note** - Remove notes
7. **obs_list_notes** - Browse vault notes
8. **obs_get_vault_structure** - Explore organization
9. **obs_execute_command** - Run Obsidian commands
10. **obs_keyword_search** - Simple content search

#### 🔧 System Tools
1. **ping** - Connectivity testing

#### 🚀 Extensible Architecture
The server is designed with a scalable architecture that makes it easy to add new applications:
- **Prefix-based routing** for clean tool organization
- **Modular client structure** in `src/clients/`
- **Consistent tool patterns** for rapid development
- **Independent service initialization** for reliability

### 📚 MCP Resources
- **Dynamic vault browsing** via `obsidian://notes/` URIs
- **Folder and note discovery** with metadata
- **Real-time resource updates** when vault changes
- **JSON-formatted folder contents** with statistics

### 🎯 MCP Prompts (5 Total)
- **note_template_system** - Learn vault organization
- **daily_note_template** - Daily note formatting
- **project_note_template** - Project note structure  
- **area_note_template** - Area note formatting
- **format_preservation_rules** - Edit guidelines

### 🏛️ Template System
- **Automatic template detection** based on folder location
- **YAML frontmatter application** for new notes
- **Format preservation** during edits
- **PARA method compliance** (Projects, Areas, Resources, Archives)
- **Template-aware tools** with `use_template` and `preserve_format` options

## 🚀 Quick Start

### Production Use (Recommended)
```bash
# Connect to live server
curl -H "Authorization: Bearer YOUR_API_KEY" \
     -H "Content-Type: application/json" \
     -X POST https://mcp.ziksaka.com/mcp \
     -d '{"jsonrpc":"2.0","method":"ping","id":1}'
```

### Local Development
```bash
# 1. Clone and setup
git clone <repository>
cd obsidian-mcp-server
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Configure environment
export MCP_API_KEY="your-api-key"
export OBSIDIAN_API_URL="http://your-obsidian-host:port"
export OBSIDIAN_API_KEY="your-obsidian-api-key"
export OBSIDIAN_VAULT_PATH="/path/to/vault"

# 3. Start development server
python main.py

# 4. Run tests and demos
python tests/test_mcp_simple.py
python demos/demo_mcp_endpoint.py
```

## 📡 API Usage

### Authentication
All requests require Bearer token authentication:
```bash
Authorization: Bearer YOUR_API_KEY
```

### Example: List Available Tools
```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
     -H "Content-Type: application/json" \
     -X POST https://mcp.ziksaka.com/mcp \
     -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

### Example: Create Note with Template
```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
     -H "Content-Type: application/json" \
     -X POST https://mcp.ziksaka.com/mcp \
     -d '{
       "jsonrpc":"2.0",
       "method":"tools/call",
       "params":{
         "name":"create_note",
         "arguments":{
           "path":"02_projects/my-project.md",
           "content":"# My Project\n\nProject description here.",
           "use_template": true
         }
       },
       "id":1
     }'
```

### Example: Browse Vault Resources
```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
     -H "Content-Type: application/json" \
     -X POST https://mcp.ziksaka.com/mcp \
     -d '{"jsonrpc":"2.0","method":"resources/read","params":{"uri":"obsidian://notes/"},"id":1}'
```

### Example: Get Template Guidance
```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
     -H "Content-Type: application/json" \
     -X POST https://mcp.ziksaka.com/mcp \
     -d '{"jsonrpc":"2.0","method":"prompts/get","params":{"name":"daily_note_template"},"id":1}'
```

## 🎯 Template System

The server automatically applies appropriate templates based on note location:

### Supported Note Types
- **Daily Notes** (`06_daily-notes/`) - Reflection templates with ratings
- **Projects** (`02_projects/`) - Goal-oriented with success criteria
- **Areas** (`03_areas/`) - Ongoing responsibilities
- **Seeds** (`01_seeds/`) - Initial ideas
- **Resources** (`04_resources/`) - External knowledge
- **Knowledge** (`05_knowledge/`) - Personal insights

### Template Features
- **YAML frontmatter** automatically applied
- **Folder-based detection** for appropriate templates
- **Format preservation** during edits
- **Customizable per note type**

## 📊 Supported Vault Structure

The server works with PARA method organization:

```
vault/
├── 01_seeds/          # Initial ideas and concepts
├── 02_projects/       # Actionable goals with deadlines
├── 03_areas/          # Ongoing responsibilities  
├── 04_resources/      # Reference materials
├── 05_knowledge/      # Personal insights
└── 06_daily-notes/    # Daily reflections
```

## 🧪 Testing

### Run Test Suite
```bash
# Unit tests
python -m pytest tests/

# Integration tests
python tests/test_mcp_endpoint.py

# Obsidian client tests
python tests/test_obsidian_client.py

# Phase-specific tests
python tests/test_phase4_resources.py
```

### Run Demonstrations
```bash
# MCP protocol demo
python demos/demo_mcp_endpoint.py

# Obsidian integration demo
python demos/demo_obsidian_integration.py

# Resources demo
python demos/demo_phase4_resources.py
```

## 🔧 Production Deployment

### Prerequisites
- VPS with systemd
- Nginx Proxy Manager (optional but recommended)
- Python 3.8+
- Obsidian with REST API plugin

### Deployment Steps
```bash
# 1. Clone to production server
git clone <repository> /path/to/production

# 2. Setup production environment
cp .env.production.example .env.production
# Edit .env.production with your settings

# 3. Install and configure systemd service
sudo cp deploy/obsidian-mcp.service /etc/systemd/system/
sudo systemctl enable obsidian-mcp
sudo systemctl start obsidian-mcp

# 4. Setup reverse proxy (optional)
# Configure Nginx Proxy Manager for HTTPS access

# 5. Verify deployment
./scripts/check-mcp.sh
```

*See [docs/deployment/](docs/deployment/) for detailed deployment guides.*

## 🏛️ Architecture

### Core Components
- **MCP Protocol Handler** - JSON-RPC 2.0 with streaming support
- **Obsidian Client** - Enhanced REST API wrapper with filesystem scanning
- **Tools Engine** - 11 comprehensive note operations
- **Resources Engine** - Dynamic vault exploration
- **Prompts Engine** - Template and format guidance
- **Template System** - Automatic format application and preservation
- **Authentication** - Bearer token security

### Data Flow
```
AI Assistant → MCP Client → HTTPS → MCP Server → Obsidian REST API → Vault
```

## 🔒 Security

- **Bearer token authentication** for all requests
- **Input validation** and sanitization
- **Error isolation** prevents information leakage
- **HTTPS encryption** in production
- **No direct file system access** (REST API only)

## 📈 Performance

- **Caching layer** for vault structure and resources (5-minute TTL)
- **Filesystem scanning** for comprehensive note discovery
- **Efficient note operations** with minimal API calls
- **Production-optimized** with `reload=False`

## 🤝 Integration

### MCP Clients
The server works with any MCP-compatible client:
- Claude Desktop
- Custom MCP implementations
- AI assistant integrations

### Obsidian Requirements
- **Obsidian** with Local REST API plugin
- **Plugin version**: 3.2.0 or later
- **API key authentication** enabled
- **HTTPS optional** but recommended

## 🛠️ Development

### Adding New Tools
1. Implement in `src/tools/obsidian_tools.py`
2. Add tests in `tests/`
3. Create demo in `demos/`
4. Update documentation

### Adding New Templates
1. Update `src/utils/template_utils.py`
2. Add prompt in `src/prompts/obsidian_prompts.py`
3. Test with create/update operations

### Debugging
```bash
# Check service status
./scripts/check-mcp.sh

# View logs
sudo journalctl -u obsidian-mcp -f

# Diagnose Obsidian connection
python scripts/diagnose_obsidian.py
```

## 📄 Documentation

- **[PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)** - Complete project organization
- **[docs/PRD.md](docs/PRD.md)** - Product requirements and specifications
- **[docs/phases/](docs/phases/)** - Development phase documentation
- **[docs/deployment/](docs/deployment/)** - Production setup guides
- **[docs/MCP_ENDPOINT.md](docs/MCP_ENDPOINT.md)** - API reference

## 💡 Example Use Cases

### For AI Assistants
- **Note creation** with automatic template application
- **Content search** with keyword and advanced queries  
- **Vault exploration** for understanding organization
- **Format-preserving edits** that respect existing structure
- **Template guidance** for proper note formatting

### For Productivity
- **Automated note organization** following PARA method
- **Consistent formatting** across all note types
- **Integrated workflows** between AI tools and Obsidian
- **Template-driven creation** for different note types

## 🎉 Success Metrics

- ✅ **11 MCP Tools** implemented and tested
- ✅ **5 MCP Prompts** for template guidance
- ✅ **Dynamic Resources** with URI navigation
- ✅ **Template System** with format preservation
- ✅ **Production Deployment** with HTTPS access
- ✅ **Comprehensive Testing** across all components
- ✅ **Full Documentation** for users and developers

## 📞 Support

For issues, questions, or contributions:
1. Check existing documentation in `docs/`
2. Run diagnostic scripts in `scripts/`
3. Review test examples in `tests/` and `demos/`
4. Consult the comprehensive `PROJECT_STRUCTURE.md`

## 📋 License

[Add your license here]

---

**Status**: Production Ready ✅ | **Version**: 1.0.0 | **Last Updated**: 2025-09-24