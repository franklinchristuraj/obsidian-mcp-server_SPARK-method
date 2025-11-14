# Obsidian MCP Server - Project Structure

This document outlines the organized structure of the Obsidian MCP Server project.

## 📁 Project Organization

```
obsidian-mcp-server/
├── 📁 src/                     # Core source code
│   ├── 📁 tools/               # MCP tools implementation
│   ├── 📁 resources/           # MCP resources implementation
│   ├── 📁 prompts/             # MCP prompts for templates
│   ├── 📁 utils/               # Utility modules
│   ├── mcp_server.py           # Main MCP protocol handler
│   ├── obsidian_client.py      # Obsidian REST API client
│   ├── auth.py                 # Authentication handling
│   └── types.py                # Type definitions
├── 📁 tests/                   # Test files
│   ├── test_mcp_*.py           # MCP protocol tests
│   ├── test_obsidian_*.py      # Obsidian integration tests
│   ├── test_phase4_*.py        # Phase-specific tests
│   └── test-*.sh               # Shell script tests
├── 📁 demos/                   # Demo and example files
│   ├── demo_mcp_*.py           # MCP functionality demos
│   ├── demo_obsidian_*.py      # Obsidian integration demos
│   └── demo_phase*.py          # Phase-specific demos
├── 📁 docs/                    # Documentation
│   ├── 📁 phases/              # Phase completion docs
│   │   ├── PHASE1_COMPLETE.md
│   │   ├── PHASE2_COMPLETE.md
│   │   ├── PHASE3_COMPLETE.md
│   │   └── PHASE4_COMPLETE.md
│   ├── 📁 deployment/          # Deployment guides
│   │   ├── DEPLOYMENT_GUIDE.md
│   │   └── PRODUCTION_SETUP.md
│   ├── PRD.md                  # Product Requirements Document
│   ├── MCP_ENDPOINT.md         # MCP endpoint documentation
│   ├── OBSIDIAN_CONNECTION_STATUS.md
│   └── setup_obsidian_api.md
├── 📁 scripts/                 # Utility scripts
│   ├── check-mcp.sh            # Health check script
│   ├── restart-mcp.sh          # Service restart script
│   ├── create_mock_server.py   # Testing utilities
│   └── diagnose_obsidian.py    # Diagnostic tools
├── 📁 deploy/                  # Deployment configurations
├── 📁 venv/                    # Python virtual environment
├── main.py                     # Development server entry point
├── main_production.py          # Production server entry point
├── config.yaml                 # Server configuration
├── requirements.txt            # Python dependencies
├── README.md                   # Main project documentation
└── PROJECT_STRUCTURE.md        # This file
```

## 🎯 Key Components

### Core Application (`src/`)
- **`mcp_server.py`** - Main MCP protocol handler with streaming support
- **`obsidian_client.py`** - Enhanced Obsidian REST API client
- **`tools/obsidian_tools.py`** - 11 MCP tools for vault operations
- **`resources/obsidian_resources.py`** - Dynamic resource discovery
- **`prompts/obsidian_prompts.py`** - Template and format guidance
- **`utils/template_utils.py`** - Template detection and application
- **`auth.py`** - API key authentication
- **`types.py`** - MCP protocol type definitions

### Testing (`tests/`)
- **Unit tests** for individual components
- **Integration tests** for MCP protocol compliance
- **End-to-end tests** for Obsidian vault operations
- **Shell scripts** for deployment testing

### Demonstrations (`demos/`)
- **MCP protocol examples** showing streaming, tools, resources
- **Obsidian integration showcases** with real vault operations
- **Phase-specific demos** highlighting completed features

### Documentation (`docs/`)
- **Phase documentation** tracking development progress
- **Deployment guides** for production setup
- **API documentation** and connection guides
- **Requirements and specifications**

### Utilities (`scripts/`)
- **Service management** scripts for production
- **Diagnostic tools** for troubleshooting
- **Testing utilities** and mock servers

## 🚀 Getting Started

### Development
```bash
# Start development server
python main.py

# Run tests
python -m pytest tests/

# Run specific demo
python demos/demo_mcp_endpoint.py
```

### Production
```bash
# Start production server
python main_production.py

# Check service status
./scripts/check-mcp.sh

# Restart service
./scripts/restart-mcp.sh
```

## 📚 Documentation Index

### Essential Reading
1. **[PRD.md](docs/PRD.md)** - Project overview and requirements
2. **[README.md](README.md)** - Quick start and usage guide
3. **[DEPLOYMENT_GUIDE.md](docs/deployment/DEPLOYMENT_GUIDE.md)** - Production setup

### Phase Documentation
- **[Phase 1](docs/phases/PHASE1_COMPLETE.md)** - Core MCP server
- **[Phase 2](docs/phases/PHASE2_COMPLETE.md)** - Obsidian client
- **[Phase 3](docs/phases/PHASE3_COMPLETE.md)** - MCP tools
- **[Phase 4](docs/phases/PHASE4_COMPLETE.md)** - MCP resources

### Technical Documentation
- **[MCP_ENDPOINT.md](docs/MCP_ENDPOINT.md)** - API reference
- **[OBSIDIAN_CONNECTION_STATUS.md](docs/OBSIDIAN_CONNECTION_STATUS.md)** - Connection setup

## 🔧 Development Workflow

### Adding New Features
1. **Implement** in appropriate `src/` subdirectory
2. **Add tests** in `tests/` with similar naming
3. **Create demo** in `demos/` to showcase functionality
4. **Update documentation** in `docs/`

### Testing
- Run unit tests: `pytest tests/test_*.py`
- Run integration tests: `pytest tests/test_*_integration.py`
- Run demos: `python demos/demo_*.py`
- Test deployment: `./scripts/check-mcp.sh`

### Deployment
- Use `scripts/` for service management
- Follow guides in `docs/deployment/`
- Monitor with `scripts/check-mcp.sh`

## 🎉 Features

### MCP Tools (11 total)
1. **ping** - Connectivity test
2. **search_notes** - Advanced note search
3. **read_note** - Read note content
4. **create_note** - Create with templates
5. **update_note** - Format-preserving updates
6. **append_note** - Add content to notes
7. **delete_note** - Remove notes
8. **list_notes** - Browse vault notes
9. **get_vault_structure** - Vault organization
10. **execute_command** - Run Obsidian commands
11. **keyword_search** - Simple keyword search

### MCP Resources
- **Dynamic discovery** of vault structure
- **URI-based navigation** (`obsidian://notes/path`)
- **Folder and note browsing** with metadata
- **Caching** for performance

### MCP Prompts (5 total)
- **Template system guidance** for AI assistants
- **Format preservation rules** for editing
- **Note type templates** (daily, project, area, etc.)

### Template System
- **Automatic template application** based on folder location
- **YAML frontmatter preservation** during edits
- **PARA method compliance** (Projects, Areas, Resources, Archives)
- **Format-aware operations** for all note types

This organized structure makes the project more maintainable, testable, and easier to navigate for both development and production use.

