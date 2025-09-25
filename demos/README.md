# Demos Directory

This directory contains demonstration scripts that showcase the capabilities of the Obsidian MCP Server.

## 🎭 Available Demos

### Core MCP Protocol Demos
- **`demo_mcp_endpoint.py`** - Complete MCP protocol demonstration
- **`demo_mcp_streaming.py`** - Server-Sent Events and streaming responses
- **`demo_phase2_simple.py`** - Simple phase 2 functionality showcase

### Obsidian Integration Demos
- **`demo_obsidian_integration.py`** - Full Obsidian vault operations
- **`demo_phase4_resources.py`** - Dynamic resource discovery and browsing

## 🚀 Running Demos

### Prerequisites
```bash
# Ensure server is running
python ../main.py

# Or use production server
# Server at https://mcp.ziksaka.com/mcp
```

### Environment Setup
```bash
# Set required environment variables
export MCP_API_KEY="your-api-key"
export OBSIDIAN_API_URL="http://localhost:4443"
export OBSIDIAN_API_KEY="your-obsidian-api-key"
export OBSIDIAN_VAULT_PATH="/path/to/vault"
```

### Run Individual Demos
```bash
# MCP protocol demonstration
python demo_mcp_endpoint.py

# Obsidian integration showcase
python demo_obsidian_integration.py

# Resources and vault browsing
python demo_phase4_resources.py

# Streaming responses
python demo_mcp_streaming.py
```

## 📋 Demo Details

### `demo_mcp_endpoint.py`
**Purpose**: Comprehensive demonstration of MCP protocol compliance

**Features Demonstrated**:
- ✅ JSON-RPC 2.0 request/response format
- ✅ Authentication with Bearer tokens
- ✅ Error handling and validation
- ✅ Method routing (`ping`, `initialize`)
- ✅ Parameter passing and validation
- ✅ Standard MCP error codes

**Expected Output**:
```
🎯 MCP Endpoint Demo
✅ Ping test passed
✅ Initialize method working
✅ Error handling correct
✅ Authentication validated
📊 All MCP protocol tests passed!
```

### `demo_obsidian_integration.py`
**Purpose**: Showcase full Obsidian vault operations

**Features Demonstrated**:
- 📝 Note creation with templates
- 📖 Note reading and metadata
- ✏️ Note updating with format preservation
- 🔍 Advanced search functionality
- 📂 Vault structure exploration
- 🏷️ Tag and link management

**Expected Output**:
```
🎯 Obsidian Integration Demo
✅ Connected to vault: franklin-vault
✅ Created note with template
✅ Read note with metadata
✅ Updated note preserving format
✅ Search functionality working
📊 All Obsidian operations successful!
```

### `demo_phase4_resources.py`
**Purpose**: Dynamic resource discovery and vault browsing

**Features Demonstrated**:
- 🌐 MCP Resources protocol compliance
- 📁 Dynamic vault structure discovery
- 🔗 URI-based navigation (`obsidian://notes/`)
- 📊 Folder content listing with metadata
- 🔄 Real-time resource updates
- 💾 Caching and performance optimization

**Expected Output**:
```
🎯 MCP Resources Demo
✅ Resource discovery active
✅ Vault root browsing: 6 folders, 12 notes
✅ Project folder: 4 active projects
✅ Daily notes: 30 days tracked
✅ URI navigation working
📊 All resource operations successful!
```

### `demo_mcp_streaming.py`
**Purpose**: Server-Sent Events and streaming response demonstration

**Features Demonstrated**:
- 📡 SSE (Server-Sent Events) streaming
- 🔄 Real-time data updates
- 📊 Progress reporting for long operations
- 🎭 Event-based architecture
- ⚡ Efficient data transfer

**Expected Output**:
```
🎯 MCP Streaming Demo
📡 Starting SSE connection...
📊 Progress: 25% - Discovering vault structure
📊 Progress: 50% - Processing notes
📊 Progress: 75% - Applying templates
📊 Progress: 100% - Complete!
✅ Streaming demonstration successful!
```

## 🎯 Demo Use Cases

### For Developers
- **Understanding MCP Protocol** - See JSON-RPC 2.0 in action
- **Learning Integration Patterns** - Obsidian REST API usage
- **Template System Exploration** - Automatic formatting
- **Performance Testing** - Streaming and caching behavior

### For Users
- **Feature Discovery** - See what the server can do
- **Workflow Examples** - Real note management scenarios
- **Template Previews** - See automatic formatting
- **Capability Assessment** - Understand integration possibilities

## 🔧 Customizing Demos

### Modifying Demo Scripts
Each demo is self-contained and easily customizable:

```python
# Example: Customize vault path in demo
VAULT_PATH = "/your/custom/vault/path"

# Example: Test different note types
NOTE_TYPES = ["project", "daily-note", "area", "seed"]

# Example: Change demo data
DEMO_NOTES = [
    {"path": "02_projects/custom-project.md", "content": "..."},
    {"path": "06_daily-notes/custom-date.md", "content": "..."}
]
```

### Creating New Demos
```python
# Template for new demo
#!/usr/bin/env python3
"""
Demo: Your Feature Name
Purpose: Demonstrate specific functionality
"""

import requests
import json
from datetime import datetime

def demo_your_feature():
    """Demonstrate your specific feature"""
    print("🎯 Your Feature Demo")
    
    # Your demo implementation
    response = requests.post(
        "http://localhost:8888/mcp",
        headers={"Authorization": "Bearer your-api-key"},
        json={"jsonrpc": "2.0", "method": "your_method", "id": 1}
    )
    
    if response.status_code == 200:
        print("✅ Your feature working!")
    else:
        print("❌ Error:", response.text)

if __name__ == "__main__":
    demo_your_feature()
```

## 📊 Demo Performance

### Timing Information
Each demo includes timing metrics:
- **Connection time** - How long to establish connection
- **Operation time** - Individual method execution time
- **Total runtime** - Complete demo execution time

### Resource Usage
Demos monitor:
- **Memory usage** - Peak memory consumption
- **Network calls** - Number of API requests
- **Cache hits** - Resource caching effectiveness

## 🔍 Debugging Demos

### Common Issues

**Connection Refused**
```bash
# Check if server is running
curl http://localhost:8888/health

# Start server if needed
python ../main.py
```

**Authentication Errors**
```bash
# Verify API key
echo $MCP_API_KEY

# Test authentication
curl -H "Authorization: Bearer $MCP_API_KEY" \
     http://localhost:8888/mcp
```

**Obsidian Connection Issues**
```bash
# Test Obsidian API directly
curl -H "Authorization: Bearer $OBSIDIAN_API_KEY" \
     $OBSIDIAN_API_URL/
```

### Verbose Mode
Most demos support verbose output:
```bash
python demo_mcp_endpoint.py --verbose
python demo_obsidian_integration.py -v
```

## 🎭 Interactive Demos

Some demos support interactive mode:
```bash
python demo_obsidian_integration.py --interactive
```

Interactive features:
- **Choose operations** - Select specific features to demonstrate
- **Custom input** - Provide your own note content
- **Step-by-step** - Pause between operations
- **Real-time feedback** - See results immediately

## 📚 Educational Value

### Learning Objectives
Each demo teaches:
- **MCP Protocol Usage** - How to interact with MCP servers
- **REST API Integration** - Obsidian plugin communication
- **Template Systems** - Automatic formatting and structure
- **Resource Management** - Dynamic discovery and caching
- **Error Handling** - Proper exception management

### Best Practices Demonstrated
- **Authentication patterns** - Secure API key usage
- **Error handling** - Graceful failure management
- **Data validation** - Input sanitization and verification
- **Performance optimization** - Caching and efficient operations

## 🎉 Success Indicators

When demos run successfully, you should see:
- ✅ **Green checkmarks** for passed operations
- 📊 **Performance metrics** showing timing
- 🎯 **Feature confirmations** with expected output
- 📋 **Summary statistics** at completion

Successful demo runs indicate:
- MCP server is properly configured
- Obsidian integration is working
- Template system is functional
- All core features are operational

## 🔄 Automated Demo Runs

For continuous testing:
```bash
# Run all demos in sequence
for demo in demo_*.py; do
    echo "Running $demo..."
    python "$demo" || echo "❌ $demo failed"
done

# Or use the provided script
./run_all_demos.sh
```

These demos provide a comprehensive showcase of the Obsidian MCP Server's capabilities and serve as excellent starting points for understanding and extending the system.
