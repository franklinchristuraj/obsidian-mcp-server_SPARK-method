# Tests Directory

This directory contains all test files for the Obsidian MCP Server.

## 🧪 Test Categories

### MCP Protocol Tests
- **`test_mcp_endpoint.py`** - Comprehensive MCP protocol compliance tests
- **`test_mcp_simple.py`** - Simple MCP functionality tests (stdlib only)
- **`test_mcp_streaming.py`** - Server-Sent Events and streaming tests

### Obsidian Integration Tests
- **`test_obsidian_client.py`** - Obsidian REST API client tests
- **`test_obsidian_tools.py`** - MCP tools functionality tests

### Feature-Specific Tests
- **`test_phase4_resources.py`** - MCP resources and vault browsing tests
- **`test_setup.py`** - Server setup and configuration tests

### Shell Script Tests
- **`test-domain-steps.sh`** - Domain and DNS configuration tests
- **`test-http-proxy.sh`** - HTTP proxy and networking tests

## 🚀 Running Tests

### Quick Tests (No Dependencies)
```bash
# Simple MCP test using only stdlib
python test_mcp_simple.py
```

### Individual Test Suites
```bash
# MCP protocol tests
python test_mcp_endpoint.py

# Obsidian client tests  
python test_obsidian_client.py

# Tools functionality tests
python test_obsidian_tools.py

# Resources and vault browsing tests
python test_phase4_resources.py
```

### Using pytest (Recommended)
```bash
# Run all tests
python -m pytest

# Run specific test file
python -m pytest test_mcp_endpoint.py

# Run with verbose output
python -m pytest -v

# Run with coverage
python -m pytest --cov=src
```

### Shell Script Tests
```bash
# Make scripts executable
chmod +x *.sh

# Run domain tests
./test-domain-steps.sh

# Run proxy tests  
./test-http-proxy.sh
```

## 📋 Test Dependencies

### Required for All Tests
- Python 3.8+
- Virtual environment activated
- Environment variables configured

### Optional Dependencies
```bash
pip install pytest pytest-cov httpx
```

### Environment Variables
```bash
export MCP_API_KEY="test-api-key"
export OBSIDIAN_API_URL="http://localhost:4443"
export OBSIDIAN_API_KEY="your-obsidian-api-key"
export OBSIDIAN_VAULT_PATH="/path/to/test/vault"
```

## 🎯 Test Coverage

### MCP Protocol Compliance ✅
- JSON-RPC 2.0 format validation
- Method routing and error handling
- Authentication and authorization
- Streaming response support

### Obsidian Integration ✅
- REST API connectivity
- CRUD operations on notes
- Vault structure discovery
- Template application and preservation

### Tools Functionality ✅
- All 11 MCP tools tested
- Parameter validation
- Error handling
- Response format verification

### Resources System ✅
- Dynamic resource discovery
- URI routing and navigation
- Folder and note browsing
- Caching behavior

### Template System ✅
- Automatic template detection
- YAML frontmatter application
- Format preservation during edits
- Note type specific templates

## 🔍 Debugging Tests

### Common Issues

**Connection Errors**
```bash
# Check Obsidian API connectivity
python ../scripts/diagnose_obsidian.py

# Verify environment variables
echo $OBSIDIAN_API_URL
echo $OBSIDIAN_API_KEY
```

**Authentication Errors**
```bash
# Test MCP API key
curl -H "Authorization: Bearer $MCP_API_KEY" \
     http://localhost:8888/mcp
```

**Template Tests Failing**
```bash
# Check vault structure
ls -la $OBSIDIAN_VAULT_PATH
```

### Verbose Testing
```bash
# Run with debug output
python test_mcp_endpoint.py --verbose

# Use pytest debug mode
python -m pytest -v -s test_obsidian_tools.py
```

## 📊 Test Reports

### Coverage Reports
```bash
# Generate coverage report
python -m pytest --cov=src --cov-report=html

# View report
open htmlcov/index.html
```

### Test Output
Each test file provides detailed output about:
- ✅ Passed tests with timing
- ❌ Failed tests with error details
- 📊 Performance metrics
- 🔍 Debug information

## 🎭 Mock Testing

Some tests use mock servers for isolated testing:
- **`create_mock_server.py`** in `../scripts/` provides mock Obsidian API
- Tests can run without real Obsidian instance
- Ideal for CI/CD pipelines

## 🚀 Continuous Integration

### Test Automation
Tests are designed to be CI/CD friendly:
- No interactive prompts
- Configurable via environment variables
- Clear pass/fail exit codes
- Detailed logging output

### Pre-commit Testing
```bash
# Run before committing changes
python -m pytest
python test_mcp_simple.py
python test_obsidian_client.py
```

## 📚 Test Documentation

Each test file includes:
- **Purpose** - What functionality is being tested
- **Requirements** - Dependencies and setup needed
- **Usage** - How to run the specific tests
- **Expected Output** - What success looks like

For more details, see the docstrings in each test file.
