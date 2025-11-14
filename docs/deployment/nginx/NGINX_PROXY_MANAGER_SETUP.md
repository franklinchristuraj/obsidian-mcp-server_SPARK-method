# Nginx Proxy Manager HTTPS Setup Guide

Complete guide for manually configuring HTTPS proxy for obsidian-mcp-server using Nginx Proxy Manager.

## Prerequisites

- ✅ Nginx Proxy Manager installed and running
- ✅ Domain/subdomain pointing to your server (or using dynamic DNS)
- ✅ obsidian-mcp-server running locally (default: `127.0.0.1:8888`)
- ✅ Ports 80 and 443 accessible from the internet

## Step 1: Verify MCP Server is Running

First, ensure your obsidian-mcp-server is running and accessible locally:

```bash
# Check if the server is running locally
curl http://127.0.0.1:8888/health

# Expected response:
# {"status":"healthy","service":"obsidian-mcp-server"}

# If Nginx Proxy Manager is on a different server, also test with public IP:
# curl http://148.230.124.28:8888/health
```

**Note:** If your MCP server is configured to listen on `0.0.0.0:8888` (all interfaces), you can use either `127.0.0.1` or your public IP. However, **using `127.0.0.1` is recommended for security** when both services are on the same server.

If the server is not running, start it:

```bash
cd /home/franklinchris/obsidian-mcp-server
source venv/bin/activate
python main.py
```

Or if using systemd service:

```bash
sudo systemctl status obsidian-mcp
sudo systemctl start obsidian-mcp  # if not running
```

## Step 2: Access Nginx Proxy Manager

1. Open your Nginx Proxy Manager web interface (typically `http://your-server-ip:81`)
2. Log in with your admin credentials

## Step 3: Create New Proxy Host

### 3.1 Basic Proxy Host Configuration

1. Click **"Proxy Hosts"** in the top menu
2. Click **"Add Proxy Host"** button
3. Fill in the **Details** tab:

| Field | Value | Notes |
|-------|-------|-------|
| **Domain Names** | `mcp.yourdomain.com` | Your subdomain for the MCP server |
| **Scheme** | `http` | Backend is HTTP |
| **Forward Hostname/IP** | `172.19.0.1` | **If Nginx Proxy Manager is in Docker** (common), use the Docker gateway IP (`172.19.0.1` - check with `docker inspect <container> \| grep Gateway`). **If running directly on host**, use `127.0.0.1`. **If on different server**, use public IP (e.g., `148.230.124.28`). |
| **Forward Port** | `8888` | Default MCP server port |
| **Cache Assets** | ❌ Unchecked | Disable for streaming/SSE |
| **Block Common Exploits** | ✅ Checked | Security |
| **Websockets Support** | ✅ Checked | Required for SSE streaming |

### 3.2 SSL Configuration

1. Go to the **SSL** tab:

| Setting | Value | Notes |
|---------|-------|-------|
| **SSL Certificate** | *Request a new SSL Certificate* | Select this option |
| **Force SSL** | ✅ Checked | Redirect HTTP to HTTPS |
| **HTTP/2 Support** | ✅ Checked | Performance |
| **HSTS Enabled** | ✅ Checked | Security |
| **HSTS Subdomains** | ✅ Checked | Include subdomains |
| **Certificate Email** | `your-email@example.com` | For Let's Encrypt notifications |

2. Click **"Save"** - Nginx Proxy Manager will automatically request a Let's Encrypt certificate

### 3.3 Advanced Configuration

Click on the **Advanced** tab and paste the following configuration:

```nginx
# CORS headers for MCP protocol
location / {
    # Handle OPTIONS requests for CORS preflight
    if ($request_method = 'OPTIONS') {
        add_header 'Access-Control-Allow-Origin' '*' always;
        add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS' always;
        add_header 'Access-Control-Allow-Headers' 'Content-Type, Authorization' always;
        add_header 'Access-Control-Max-Age' 1728000 always;
        add_header 'Content-Type' 'text/plain charset=UTF-8' always;
        add_header 'Content-Length' 0 always;
        return 204;
    }

    # Proxy to MCP server
    # IMPORTANT: If Nginx Proxy Manager is in Docker, use Docker gateway IP (e.g., 172.19.0.1)
    # Find gateway IP with: docker inspect <container> | grep Gateway
    # If running directly on host, use: 127.0.0.1
    proxy_pass http://172.19.0.1:8888;
    proxy_http_version 1.1;

    # Preserve host and client info
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;

    # CORS headers for actual requests
    add_header 'Access-Control-Allow-Origin' '*' always;
    add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS' always;
    add_header 'Access-Control-Allow-Headers' 'Content-Type, Authorization' always;

    # SSE/Streaming configuration
    proxy_buffering off;
    proxy_request_buffering off;
    proxy_cache off;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
    proxy_connect_timeout 60s;
    add_header X-Accel-Buffering no;

    # WebSocket support
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}

# Health check endpoint (no auth required)
location /health {
    # Use Docker gateway IP if in Docker (172.19.0.1), or 127.0.0.1 if on host
    proxy_pass http://172.19.0.1:8888/health;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

**Note:** If your MCP server is exposed at `/mcp` path instead of root, modify the configuration:

```nginx
location /mcp {
    # ... same configuration as above ...
    # Use Docker gateway IP if in Docker (172.19.0.1), or 127.0.0.1 if on host
    proxy_pass http://172.19.0.1:8888/mcp;  # Note the /mcp path
}

location /health {
    # Use same IP as main location block
    proxy_pass http://172.19.0.1:8888/health;
    # ... same headers ...
}
```

### 3.4 Optional: Access Control

If you want to restrict access, you can add IP whitelisting in the Advanced tab:

```nginx
# Restrict access to specific IPs (optional)
location / {
    # Allow specific IPs or CIDR ranges
    allow 203.0.113.0/24;  # Replace with your IP range
    allow 198.51.100.0/24;  # Additional IP range
    deny all;
    
    # ... rest of proxy configuration ...
}
```

Or use Nginx Proxy Manager's built-in **Access Lists** feature:
1. Go to **Access Lists** → **Add Access List**
2. Create a list with allowed IPs
3. Go back to your Proxy Host → **Access** tab
4. Select your access list

## Step 4: Verify Configuration

### 4.1 Check SSL Certificate

Wait a few minutes for Let's Encrypt to issue the certificate, then verify:

```bash
# Check certificate status
curl -I https://mcp.yourdomain.com/health

# Expected: HTTP/2 200 or similar
```

### 4.2 Test MCP Endpoint

Test the MCP endpoint with authentication:

```bash
# Set your API key
export MCP_API_KEY="your-api-key-here"

# Test health endpoint (no auth required)
curl https://mcp.yourdomain.com/health

# Test MCP endpoint (auth required)
curl -X POST https://mcp.yourdomain.com/mcp \
  -H "Authorization: Bearer $MCP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "initialize",
    "id": 1,
    "params": {
      "protocolVersion": "2024-11-05",
      "capabilities": {},
      "clientInfo": {
        "name": "test-client",
        "version": "1.0.0"
      }
    }
  }'
```

### 4.3 Test CORS (if accessing from browser)

If you need to access the MCP server from a browser, verify CORS:

```bash
curl -X OPTIONS https://mcp.yourdomain.com/mcp \
  -H "Origin: https://your-client-domain.com" \
  -H "Access-Control-Request-Method: POST" \
  -v
```

You should see CORS headers in the response.

## Step 5: Configure Firewall (Optional but Recommended)

Ensure only necessary ports are open:

```bash
# Allow SSH
sudo ufw allow 22/tcp

# Allow HTTP/HTTPS (managed by Nginx Proxy Manager)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Allow Nginx Proxy Manager admin interface (if exposed)
sudo ufw allow 81/tcp

# Block direct access to MCP server port
sudo ufw deny 8888/tcp

# Enable firewall
sudo ufw enable
sudo ufw status
```

## Step 6: Update Client Configuration

Update your MCP client to use the HTTPS endpoint:

```json
{
  "mcpServers": {
    "obsidian": {
      "url": "https://mcp.yourdomain.com/mcp",
      "headers": {
        "Authorization": "Bearer your-api-key-here"
      }
    }
  }
}
```

## Troubleshooting

### SSL Certificate Not Issuing

1. **DNS not propagated**: Ensure DNS A record points to your server IP
2. **Port 80 blocked**: Let's Encrypt needs port 80 open for validation
3. **Rate limiting**: Wait 5-7 days if you've hit Let's Encrypt limits
4. **Check logs**: View Nginx Proxy Manager logs in the web interface

### 502 Bad Gateway

1. **Check MCP server is running**:
   ```bash
   curl http://127.0.0.1:8888/health
   ```

2. **Verify Forward Hostname/IP**: 
   - **If Nginx Proxy Manager is in Docker** (most common): Use Docker gateway IP (`172.19.0.1` - find with `docker inspect <container> | grep Gateway`)
   - **If running directly on host**: Use `127.0.0.1`
   - **If on different server**: Use the public IP (e.g., `148.230.124.28`)
   - Test from container: `docker exec <container> wget -O- http://<hostname>:8888/health` (if wget available)
   - Test from host: `curl http://127.0.0.1:8888/health`

3. **Check Nginx Proxy Manager logs**: Look for connection errors

4. **Verify port**: Ensure MCP server is on port 8888:
   ```bash
   netstat -tlnp | grep 8888
   # or
   ss -tlnp | grep 8888
   ```

### CORS Errors

1. Verify CORS headers are present in Advanced configuration
2. Check browser console for specific CORS errors
3. Ensure `Access-Control-Allow-Origin` header is set correctly

### Connection Timeouts

1. Increase timeout values in Advanced configuration:
   ```nginx
   proxy_read_timeout 3600s;
   proxy_send_timeout 3600s;
   proxy_connect_timeout 60s;
   ```

2. Check MCP server logs for slow operations

### Authentication Issues

1. Verify API key is set correctly in client
2. Check MCP server logs for authentication errors
3. Ensure `Authorization: Bearer <key>` header format is correct

## Security Checklist

- ✅ SSL certificate valid and auto-renewing
- ✅ Force SSL enabled (HTTP → HTTPS redirect)
- ✅ Direct port access blocked (firewall)
- ✅ Strong API key configured
- ✅ CORS configured appropriately (not too permissive)
- ✅ Access control configured (if needed)
- ✅ HSTS enabled for browser security
- ✅ Regular backups of configuration

## Maintenance

### Renew SSL Certificate

Nginx Proxy Manager handles renewal automatically, but you can manually renew:

1. Go to **SSL Certificates**
2. Find your certificate
3. Click **Renew** (if available)

### Update Configuration

1. Go to **Proxy Hosts**
2. Click on your proxy host
3. Edit configuration as needed
4. Click **Save**

### View Logs

1. Go to **Proxy Hosts**
2. Click on your proxy host
3. Click **Logs** tab to view access/error logs

## Next Steps

- Configure monitoring/health checks
- Set up automated backups
- Configure log rotation
- Set up alerts for downtime

---

**Your HTTPS proxy is now configured!** 🎉

Access your MCP server at: `https://mcp.yourdomain.com/mcp`

