# Production Setup - VPS Direct Deployment

## 🎯 Current Status
✅ Project built on VPS at `/root/obsidian-mcp-server`  
✅ Virtual environment ready  
✅ All dependencies installed  
✅ Testing complete and working  

## 🚀 Production Configuration Steps

### 1. Create Production Environment File

```bash
# Create production environment
cd /root/obsidian-mcp-server
cp .env .env.production

# Edit for production
nano .env.production
```

**Production Environment Settings:**
```bash
# Server Configuration - Production
MCP_HOST=127.0.0.1
MCP_PORT=8888
MCP_API_KEY=generate-secure-32-char-key-here

# Obsidian Configuration (Update paths as needed)
OBSIDIAN_API_URL=http://127.0.0.1:4443
OBSIDIAN_API_KEY=YOUR_OBSIDIAN_API_KEY
OBSIDIAN_VAULT_PATH=/root/obsidian/franklin-vault

# Production Settings
MCP_LOG_LEVEL=INFO
MCP_ENABLE_CORS=false
```

**Generate secure API key:**
```bash
openssl rand -hex 32
```

### 2. Update Main.py for Production

Create production startup script:
```bash
nano main_production.py
```

```python
#!/usr/bin/env python3
"""
Obsidian MCP Server - Production Entry Point
"""
import uvicorn
import os
from dotenv import load_dotenv

# Load production environment
load_dotenv('.env.production')

if __name__ == "__main__":
    # Production configuration
    uvicorn.run(
        "main:app",
        host=os.getenv("MCP_HOST", "127.0.0.1"),
        port=int(os.getenv("MCP_PORT", 8888)),
        workers=1,  # Single worker for now
        log_level=os.getenv("MCP_LOG_LEVEL", "info").lower(),
        access_log=True,
        reload=False  # Disabled for production
    )
```

### 3. Create systemd Service

```bash
sudo nano /etc/systemd/system/obsidian-mcp.service
```

```ini
[Unit]
Description=Obsidian MCP Server
After=network.target
Wants=network.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/root/obsidian-mcp-server
Environment="PATH=/root/obsidian-mcp-server/venv/bin"
EnvironmentFile=/root/obsidian-mcp-server/.env.production
ExecStart=/root/obsidian-mcp-server/venv/bin/python main_production.py
Restart=always
RestartSec=10

# Security (relaxed for root user setup)
NoNewPrivileges=true
PrivateTmp=true

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=obsidian-mcp

[Install]
WantedBy=multi-user.target
```

### 4. Set File Permissions & Enable Service

```bash
# Secure environment file
chmod 600 .env.production

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable obsidian-mcp
sudo systemctl start obsidian-mcp

# Check status
sudo systemctl status obsidian-mcp
```

### 5. Configure Nginx Proxy Manager

In your existing Nginx Proxy Manager interface:

**Add New Proxy Host:**
- **Domain Names**: `mcp.yourdomain.com` (or your chosen subdomain)
- **Scheme**: `http`
- **Forward Hostname/IP**: `127.0.0.1`
- **Forward Port**: `8888`
- **Block Common Exploits**: ✅ Enabled
- **Websockets Support**: ✅ Enabled

**SSL Tab:**
- **SSL Certificate**: Request a new SSL Certificate (Let's Encrypt)
- **Force SSL**: ✅ Enabled
- **HTTP/2 Support**: ✅ Enabled
- **HSTS Enabled**: ✅ Enabled

**Advanced Tab (Optional for better performance):**
```nginx
# Custom Nginx Configuration
location /mcp {
    proxy_pass http://127.0.0.1:8888;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    
    # Timeout settings for MCP operations
    proxy_connect_timeout 60s;
    proxy_send_timeout 60s;
    proxy_read_timeout 60s;
    
    # Disable buffering for SSE streaming
    proxy_buffering off;
    proxy_cache off;
}
```

### 6. Test Production Deployment

```bash
# Test local service
curl -H "Authorization: Bearer your-production-api-key" \
     -H "Content-Type: application/json" \
     -X POST http://127.0.0.1:8888/mcp \
     -d '{"jsonrpc":"2.0","method":"ping","id":1}'

# Test through Nginx proxy (replace with your domain)
curl -H "Authorization: Bearer your-production-api-key" \
     -H "Content-Type: application/json" \
     -X POST https://mcp.yourdomain.com/mcp \
     -d '{"jsonrpc":"2.0","method":"ping","id":1}'

# Test resources
curl -H "Authorization: Bearer your-production-api-key" \
     -H "Content-Type: application/json" \
     -X POST https://mcp.yourdomain.com/mcp \
     -d '{"jsonrpc":"2.0","method":"resources/list","id":1}'
```

### 7. Create Maintenance Scripts

**Restart Script:**
```bash
nano restart-mcp.sh
chmod +x restart-mcp.sh
```

```bash
#!/bin/bash
echo "🔄 Restarting Obsidian MCP Server..."
sudo systemctl restart obsidian-mcp
sleep 3
sudo systemctl status obsidian-mcp
echo "✅ Restart complete"
```

**Status Check Script:**
```bash
nano check-mcp.sh
chmod +x check-mcp.sh
```

```bash
#!/bin/bash
echo "📊 Obsidian MCP Server Status:"
echo "================================"
sudo systemctl status obsidian-mcp
echo ""
echo "🔗 Testing connectivity:"
curl -s -H "Authorization: Bearer $(grep MCP_API_KEY .env.production | cut -d'=' -f2)" \
     -H "Content-Type: application/json" \
     -X POST http://127.0.0.1:8888/mcp \
     -d '{"jsonrpc":"2.0","method":"ping","id":1}' | jq .
```

**Log Viewer:**
```bash
nano view-logs.sh
chmod +x view-logs.sh
```

```bash
#!/bin/bash
echo "📜 Obsidian MCP Server Logs (last 50 lines):"
echo "============================================="
sudo journalctl -u obsidian-mcp -n 50 --no-pager
echo ""
echo "📡 Live log streaming (Ctrl+C to exit):"
sudo journalctl -u obsidian-mcp -f
```

### 8. Firewall Configuration

```bash
# If using ufw, allow only necessary ports
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Block direct access to MCP port (optional security)
sudo ufw deny 8888/tcp

# Enable firewall
sudo ufw --force enable
sudo ufw status
```

## 🔧 Daily Operations

**View Service Status:**
```bash
sudo systemctl status obsidian-mcp
# or
./check-mcp.sh
```

**View Logs:**
```bash
sudo journalctl -u obsidian-mcp -f
# or
./view-logs.sh
```

**Restart Service:**
```bash
sudo systemctl restart obsidian-mcp
# or
./restart-mcp.sh
```

**Update Code (if needed):**
```bash
cd /root/obsidian-mcp-server
git pull  # if using git
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart obsidian-mcp
```

## 📊 Monitoring & Health

**Service Health Check:**
```bash
# Create health check endpoint test
curl -H "Authorization: Bearer your-api-key" \
     -H "Content-Type: application/json" \
     -X POST https://mcp.yourdomain.com/mcp \
     -d '{"jsonrpc":"2.0","method":"ping","id":1}'
```

**Resource Usage:**
```bash
# Check memory and CPU usage
htop
# or
ps aux | grep python | grep mcp
```

## 🛡️ Security Notes

✅ **API Key**: Strong 32-character key generated  
✅ **Environment**: Production settings loaded from secure file  
✅ **Network**: Service bound to localhost (127.0.0.1)  
✅ **Proxy**: HTTPS termination at Nginx Proxy Manager  
✅ **Firewall**: Direct port access blocked  

## 🎯 Success Criteria

- ✅ Service starts automatically on boot
- ✅ HTTPS access through your domain
- ✅ All MCP methods working
- ✅ Resources browsing functional  
- ✅ Logs being captured
- ✅ Health checks passing

## 🆘 Troubleshooting

**Service won't start:**
```bash
sudo journalctl -u obsidian-mcp --no-pager -l
```

**Can't connect through domain:**
- Check Nginx Proxy Manager configuration
- Verify domain DNS settings
- Test local connection first

**Performance issues:**
```bash
# Check system resources
htop
# Check service logs
sudo journalctl -u obsidian-mcp -n 100
```

---

## 🎉 Your MCP Server is Production Ready!

Access at: `https://mcp.yourdomain.com/mcp`

All your Obsidian vault resources are now accessible via MCP protocol with:
- ✅ 10 MCP Tools for vault manipulation
- ✅ Dynamic resource browsing via `obsidian://notes/{path}`
- ✅ HTTPS security
- ✅ Auto-restart on failure
- ✅ Professional logging
