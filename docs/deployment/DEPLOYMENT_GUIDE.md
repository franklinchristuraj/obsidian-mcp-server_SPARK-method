# Obsidian MCP Server - Production Deployment Guide

## 📋 Prerequisites

- ✅ VPS with Ubuntu 22.04+ or Debian 11+
- ✅ Python 3.10+
- ✅ Nginx Proxy Manager (already configured)
- ✅ Domain/subdomain for the service
- ✅ 2GB+ RAM recommended
- ✅ 10GB+ storage

## 🚀 Step-by-Step Deployment

### 1. Clone & Setup on VPS

```bash
# Clone the repository
cd /opt
sudo git clone <your-repo-url> obsidian-mcp-server
sudo chown -R $USER:$USER /opt/obsidian-mcp-server
cd /opt/obsidian-mcp-server

# Create Python virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Environment Configuration

Create production environment file:

```bash
# Create production environment file
sudo nano /opt/obsidian-mcp-server/.env.production
```

Add the following configuration:

```bash
# Server Configuration
MCP_HOST=127.0.0.1
MCP_PORT=8888
MCP_API_KEY=your-secure-api-key-here-change-this

# Obsidian REST API Configuration
OBSIDIAN_API_URL=http://127.0.0.1:4443
OBSIDIAN_API_KEY=YOUR_OBSIDIAN_API_KEY
OBSIDIAN_VAULT_PATH=/path/to/your/obsidian/vault

# Logging
MCP_LOG_LEVEL=INFO
MCP_ENABLE_CORS=false
```

**Important:** 
- Generate a strong `MCP_API_KEY` using: `openssl rand -hex 32`
- Update paths to match your VPS setup
- Set `MCP_HOST=127.0.0.1` for security (Nginx will proxy)

### 3. Create systemd Service

```bash
# Create systemd service file
sudo nano /etc/systemd/system/obsidian-mcp.service
```

Add the following configuration:

```ini
[Unit]
Description=Obsidian MCP Server
After=network.target
Wants=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/obsidian-mcp-server
Environment="PATH=/opt/obsidian-mcp-server/venv/bin"
EnvironmentFile=/opt/obsidian-mcp-server/.env.production
ExecStart=/opt/obsidian-mcp-server/venv/bin/python main.py
Restart=always
RestartSec=10

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/obsidian-mcp-server

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=obsidian-mcp

[Install]
WantedBy=multi-user.target
```

### 4. Configure Service Permissions

```bash
# Set proper ownership
sudo chown -R www-data:www-data /opt/obsidian-mcp-server

# Make sure environment file is secure
sudo chmod 600 /opt/obsidian-mcp-server/.env.production

# Reload systemd and enable service
sudo systemctl daemon-reload
sudo systemctl enable obsidian-mcp
sudo systemctl start obsidian-mcp

# Check service status
sudo systemctl status obsidian-mcp
```

### 5. Nginx Proxy Manager Configuration

Since you already have Nginx Proxy Manager, create a new proxy host:

**Proxy Host Settings:**
- **Domain Names**: `your-domain.com` or `mcp.your-domain.com`
- **Forward Hostname/IP**: `127.0.0.1`
- **Forward Port**: `8888`
- **Block Common Exploits**: ✅ Enabled
- **Websockets Support**: ✅ Enabled (for SSE streaming)

**SSL Settings:**
- **SSL Certificate**: Let's Encrypt or your existing certificate
- **Force SSL**: ✅ Enabled
- **HTTP/2 Support**: ✅ Enabled
- **HSTS Enabled**: ✅ Enabled

**Advanced Configuration (Optional):**
```nginx
# Add these custom locations for better performance
location /mcp {
    proxy_pass http://127.0.0.1:8888;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    
    # Timeouts for long-running requests
    proxy_connect_timeout 60s;
    proxy_send_timeout 60s;
    proxy_read_timeout 60s;
    
    # Buffer settings for streaming
    proxy_buffering off;
    proxy_cache off;
}
```

### 6. Firewall Configuration

```bash
# Allow only necessary ports (Nginx Proxy Manager handles HTTPS)
sudo ufw allow ssh
sudo ufw allow 80
sudo ufw allow 443

# Enable firewall
sudo ufw enable

# Block direct access to MCP server port
sudo ufw deny 8888
```

### 7. Logging & Monitoring Setup

```bash
# Create log rotation configuration
sudo nano /etc/logrotate.d/obsidian-mcp
```

Add the following:

```
/var/log/obsidian-mcp/*.log {
    daily
    missingok
    rotate 52
    compress
    delaycompress
    notifempty
    create 644 www-data www-data
    postrotate
        systemctl reload obsidian-mcp
    endscript
}
```

### 8. Health Check & Monitoring

Create a health check script:

```bash
# Create monitoring script
sudo nano /opt/obsidian-mcp-server/health-check.sh
sudo chmod +x /opt/obsidian-mcp-server/health-check.sh
```

```bash
#!/bin/bash
# Health check script for Obsidian MCP Server

API_KEY="your-secure-api-key-here"
ENDPOINT="https://your-domain.com/mcp"

# Test basic connectivity
response=$(curl -s -w "%{http_code}" -H "Authorization: Bearer $API_KEY" \
           -H "Content-Type: application/json" \
           -X POST "$ENDPOINT" \
           -d '{"jsonrpc":"2.0","method":"ping","id":1}' \
           -o /dev/null)

if [ "$response" = "200" ]; then
    echo "✅ MCP Server is healthy"
    exit 0
else
    echo "❌ MCP Server health check failed (HTTP $response)"
    exit 1
fi
```

### 9. Backup Strategy

```bash
# Create backup script
sudo nano /opt/obsidian-mcp-server/backup.sh
sudo chmod +x /opt/obsidian-mcp-server/backup.sh
```

```bash
#!/bin/bash
# Backup script for Obsidian MCP Server configuration

BACKUP_DIR="/opt/backups/obsidian-mcp"
DATE=$(date +%Y%m%d_%H%M%S)

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Backup configuration files
tar -czf "$BACKUP_DIR/obsidian-mcp-config-$DATE.tar.gz" \
    /opt/obsidian-mcp-server/.env.production \
    /opt/obsidian-mcp-server/config.yaml \
    /etc/systemd/system/obsidian-mcp.service

# Keep only last 30 days of backups
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +30 -delete

echo "✅ Configuration backup completed: obsidian-mcp-config-$DATE.tar.gz"
```

### 10. Testing Production Deployment

```bash
# Test local service
curl -H "Authorization: Bearer your-api-key" \
     -H "Content-Type: application/json" \
     -X POST http://127.0.0.1:8888/mcp \
     -d '{"jsonrpc":"2.0","method":"ping","id":1}'

# Test through Nginx proxy
curl -H "Authorization: Bearer your-api-key" \
     -H "Content-Type: application/json" \
     -X POST https://your-domain.com/mcp \
     -d '{"jsonrpc":"2.0","method":"ping","id":1}'

# Test resource listing
curl -H "Authorization: Bearer your-api-key" \
     -H "Content-Type: application/json" \
     -X POST https://your-domain.com/mcp \
     -d '{"jsonrpc":"2.0","method":"resources/list","id":1}'
```

## 🔧 Maintenance Commands

```bash
# View service logs
sudo journalctl -u obsidian-mcp -f

# Restart service
sudo systemctl restart obsidian-mcp

# Check service status
sudo systemctl status obsidian-mcp

# Update deployment
cd /opt/obsidian-mcp-server
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart obsidian-mcp
```

## 🛡️ Security Checklist

- ✅ Strong API key generated and configured
- ✅ Service running as non-root user (www-data)
- ✅ Direct port access blocked by firewall
- ✅ HTTPS enforced through Nginx Proxy Manager
- ✅ Environment file permissions secured (600)
- ✅ systemd security settings enabled
- ✅ Log rotation configured
- ✅ Regular backups scheduled

## 📊 Performance Tuning

For high-traffic deployments:

1. **Increase worker processes** in `main.py`:
   ```python
   uvicorn.run("main:app", host="127.0.0.1", port=8888, workers=4)
   ```

2. **Add Redis caching** (optional):
   ```bash
   pip install redis
   # Configure Redis for vault structure caching
   ```

3. **Monitor resource usage**:
   ```bash
   # Add to crontab for monitoring
   */5 * * * * /opt/obsidian-mcp-server/health-check.sh
   ```

## 🎯 Success Criteria

✅ Service running and accessible via HTTPS  
✅ All MCP methods responding correctly  
✅ Resource discovery working  
✅ SSL certificate valid and auto-renewing  
✅ Logs being captured and rotated  
✅ Health checks passing  
✅ Backup strategy in place  

## 🆘 Troubleshooting

**Service won't start:**
```bash
sudo journalctl -u obsidian-mcp --no-pager -l
```

**Can't connect through proxy:**
- Check Nginx Proxy Manager logs
- Verify port 8888 is accessible locally
- Check firewall rules

**SSL issues:**
- Verify domain DNS settings
- Check Let's Encrypt rate limits
- Ensure port 80/443 are accessible

**Performance issues:**
- Monitor server resources: `htop`
- Check log file sizes
- Review cache hit ratios

---

**🎉 Your Obsidian MCP Server is now ready for production!**

Access your vault remotely through: `https://your-domain.com/mcp`
