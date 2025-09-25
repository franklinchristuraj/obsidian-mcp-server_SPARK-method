# Scripts Directory

This directory contains utility scripts for managing, testing, and diagnosing the Obsidian MCP Server.

## 🛠️ Available Scripts

### Service Management
- **`check-mcp.sh`** - Health check and status monitoring
- **`restart-mcp.sh`** - Restart the systemd service

### Diagnostic Tools
- **`diagnose_obsidian.py`** - Obsidian API connectivity diagnostics
- **`create_mock_server.py`** - Mock server for testing

### Network Testing
- **`test-http-proxy.sh`** - HTTP proxy and networking tests
- **`test-domain-steps.sh`** - Domain and DNS configuration verification

## 🚀 Script Usage

### Service Management Scripts

#### `check-mcp.sh` - Health Check
**Purpose**: Monitor server status and test connectivity

```bash
# Basic health check
./check-mcp.sh

# Expected output:
# ● obsidian-mcp.service - Obsidian MCP Server
#      Active: active (running) since Wed 2025-09-24 20:58:17 UTC
# 🎯 Testing MCP server connectivity...
# ✅ MCP server responding correctly
```

**Features**:
- ✅ Systemd service status check
- ✅ Local connectivity test with ping
- ✅ API authentication verification
- ✅ JSON response validation
- ✅ Performance timing metrics

#### `restart-mcp.sh` - Service Restart
**Purpose**: Safely restart the production service

```bash
# Restart service
./restart-mcp.sh

# Expected output:
# 🔄 Restarting Obsidian MCP service...
# ✅ Service restarted successfully
```

**Features**:
- 🔄 Graceful service restart
- ⏱️ Automatic wait for startup
- ✅ Post-restart health verification
- 📊 Status confirmation

### Diagnostic Tools

#### `diagnose_obsidian.py` - Obsidian Diagnostics
**Purpose**: Comprehensive Obsidian API connectivity testing

```bash
# Run diagnostics
python diagnose_obsidian.py

# With verbose output
python diagnose_obsidian.py --verbose
```

**Features Tested**:
- 🔗 **Network connectivity** to Obsidian API host
- 🔐 **Authentication** with API key
- 📡 **API endpoint availability** and responses
- 📁 **Vault accessibility** and structure
- ⚡ **Performance metrics** and timing
- 🚨 **Error detection** and troubleshooting tips

**Sample Output**:
```
🎯 Obsidian API Diagnostics
🔗 Testing connection to http://148.230.124.28:4443...
✅ Network connectivity: OK (Response time: 45ms)
🔐 Testing authentication...
✅ Authentication: Valid API key
📡 Testing API endpoints...
✅ Root endpoint: Available
✅ Vault endpoint: Accessible
📁 Testing vault access...
✅ Vault path: /root/obsidian/franklin-vault
✅ Vault structure: 6 folders, 127 notes
📊 Performance Summary:
   - Average response time: 52ms
   - Cache hit rate: 85%
   - Error rate: 0%
✅ All diagnostics passed!
```

#### `create_mock_server.py` - Mock Testing Server
**Purpose**: Create mock Obsidian API for isolated testing

```bash
# Start mock server
python create_mock_server.py

# Start on custom port
python create_mock_server.py --port 8080

# With debug logging
python create_mock_server.py --debug
```

**Features**:
- 🎭 **Mock Obsidian API** endpoints
- 📝 **Simulated note operations** (CRUD)
- 📁 **Virtual vault structure**
- 🔐 **Configurable authentication**
- 📊 **Request logging** and metrics
- 🚀 **Perfect for CI/CD testing**

### Network Testing Scripts

#### `test-http-proxy.sh` - Proxy Testing
**Purpose**: Test HTTP proxy configuration and networking

```bash
# Test proxy setup
./test-http-proxy.sh

# Test specific domain
./test-http-proxy.sh mcp.ziksaka.com
```

**Tests Performed**:
- 🌐 DNS resolution
- 🔗 HTTP connectivity  
- 🛡️ HTTPS/SSL verification
- 🔄 Proxy routing (if configured)
- ⚡ Response time measurement

#### `test-domain-steps.sh` - Domain Configuration
**Purpose**: Verify domain and DNS configuration

```bash
# Test domain setup
./test-domain-steps.sh

# Test specific domain
./test-domain-steps.sh your-domain.com
```

**Verification Steps**:
- 📍 **DNS A record** resolution
- 🌐 **Domain accessibility** from internet
- 🔒 **SSL certificate** validity
- 🔄 **Redirect configuration** (HTTP to HTTPS)
- 📊 **Performance metrics**

## 🔧 Script Configuration

### Environment Variables
Most scripts use these environment variables:

```bash
# MCP Server Configuration
export MCP_HOST="0.0.0.0"
export MCP_PORT="8888"
export MCP_API_KEY="your-mcp-api-key"

# Obsidian Configuration  
export OBSIDIAN_API_URL="http://localhost:4443"
export OBSIDIAN_API_KEY="your-obsidian-api-key"
export OBSIDIAN_VAULT_PATH="/path/to/vault"

# Production Configuration
export PRODUCTION_HOST="mcp.ziksaka.com"
export PRODUCTION_API_KEY="production-api-key"
```

### Script Parameters
Many scripts accept command-line parameters:

```bash
# Health check with custom endpoint
./check-mcp.sh --endpoint https://mcp.ziksaka.com/mcp

# Diagnostics with custom timeout
python diagnose_obsidian.py --timeout 30

# Mock server with custom configuration
python create_mock_server.py --port 8080 --vault-path /custom/vault
```

## 📊 Monitoring and Alerting

### Automated Health Checks
Set up cron jobs for automated monitoring:

```bash
# Add to crontab for 5-minute checks
*/5 * * * * /path/to/scripts/check-mcp.sh > /var/log/mcp-health.log 2>&1

# Daily comprehensive diagnostics
0 6 * * * /path/to/scripts/diagnose_obsidian.py --report > /var/log/mcp-daily.log 2>&1
```

### Log Analysis
Scripts generate structured logs for analysis:

```bash
# View recent health check logs
tail -f /var/log/mcp-health.log

# Analyze performance trends
grep "Response time" /var/log/mcp-health.log | tail -20

# Check error patterns
grep "ERROR\|❌" /var/log/mcp-*.log
```

## 🚨 Troubleshooting

### Common Issues and Solutions

**Service Won't Start**
```bash
# Check service status
sudo systemctl status obsidian-mcp

# Check configuration
python diagnose_obsidian.py

# Review logs
sudo journalctl -u obsidian-mcp -f
```

**Connection Refused**
```bash
# Test network connectivity
./test-http-proxy.sh

# Check firewall
sudo ufw status

# Verify port binding
netstat -tlnp | grep 8888
```

**Authentication Failures**
```bash
# Verify API keys
echo $MCP_API_KEY
echo $OBSIDIAN_API_KEY

# Test authentication
curl -H "Authorization: Bearer $MCP_API_KEY" http://localhost:8888/mcp
```

**Performance Issues**
```bash
# Run performance diagnostics
python diagnose_obsidian.py --performance

# Check system resources
top -p $(pgrep python)

# Analyze response times
./check-mcp.sh --timing
```

## 🔄 Development Workflow

### Pre-deployment Testing
```bash
# Run full diagnostic suite
python diagnose_obsidian.py
./test-http-proxy.sh
./test-domain-steps.sh

# Verify service configuration
./check-mcp.sh --config-check
```

### Post-deployment Verification
```bash
# Restart and verify
./restart-mcp.sh

# Comprehensive health check
./check-mcp.sh --full

# Performance baseline
python diagnose_obsidian.py --benchmark
```

### Continuous Monitoring
```bash
# Real-time monitoring
watch -n 30 './check-mcp.sh --quiet'

# Long-term logging
nohup ./check-mcp.sh --loop --interval 300 > mcp-monitor.log &
```

## 📈 Performance Optimization

### Script Performance
- **Parallel execution** where possible
- **Caching** of repeated checks
- **Timeout management** for network operations
- **Resource cleanup** after operations

### Monitoring Efficiency
- **Batch operations** to reduce overhead
- **Smart scheduling** to avoid peak times
- **Alerting thresholds** to minimize noise
- **Log rotation** to manage disk space

## 🎯 Best Practices

### Script Usage
- ✅ **Run diagnostics** before reporting issues
- ✅ **Use verbose mode** for troubleshooting
- ✅ **Check logs** for detailed error information
- ✅ **Test network connectivity** first
- ✅ **Verify configuration** before service operations

### Production Monitoring
- ✅ **Automated health checks** every 5 minutes
- ✅ **Daily comprehensive diagnostics**
- ✅ **Log retention** for historical analysis
- ✅ **Alert on consecutive failures**
- ✅ **Performance trend monitoring**

### Security Considerations
- 🔐 **Protect API keys** in environment variables
- 🔒 **Limit script permissions** appropriately
- 📝 **Log security events** for audit trails
- 🚨 **Monitor for unauthorized access attempts**

These scripts provide comprehensive management and monitoring capabilities for the Obsidian MCP Server, ensuring reliable operation and quick issue resolution.
