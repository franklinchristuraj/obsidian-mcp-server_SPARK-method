# Nginx Proxy Manager Setup for ziksaka.com

## 🎯 Goal
Expose Obsidian MCP Server at `https://mcp.ziksaka.com/mcp`

## ✅ Prerequisites Check

- ✅ Domain: `ziksaka.com`
- ✅ MCP Server: Running on `127.0.0.1:8888`
- ✅ Nginx Proxy Manager: Available on port 9443

## 📋 Step-by-Step Configuration

### Step 1: DNS Configuration

**Before configuring NPM, ensure DNS is set up:**

1. Go to your DNS provider (where ziksaka.com is managed)
2. Add an **A record**:
   - **Name**: `mcp` (or `mcp.ziksaka.com` depending on provider)
   - **Type**: A
   - **Value**: `148.230.124.28` (your server IP)
   - **TTL**: 300 (or default)

**Verify DNS propagation:**
```bash
# Check if DNS resolves
dig mcp.ziksaka.com
# or
nslookup mcp.ziksaka.com
```

### Step 2: Access Nginx Proxy Manager

1. Open your browser
2. Navigate to: `https://148.230.124.28:9443` (or your NPM domain)
3. Log in with your admin credentials

### Step 3: Create Proxy Host

1. Click **"Proxy Hosts"** in the top menu
2. Click **"Add Proxy Host"** button

#### Details Tab:

| Field | Value | Notes |
|-------|-------|-------|
| **Domain Names** | `mcp.ziksaka.com` | Your subdomain |
| **Scheme** | `http` | Backend is HTTP |
| **Forward Hostname/IP** | `127.0.0.1` | Localhost (same server) |
| **Forward Port** | `8888` | MCP server port |
| **Cache Assets** | ❌ Unchecked | Disable for streaming |
| **Block Common Exploits** | ✅ Checked | Security |
| **Websockets Support** | ✅ Checked | Required for SSE |

**Note:** If NPM is running in Docker, you might need to use `172.19.0.1` or `host.docker.internal` instead of `127.0.0.1`. Check with:
```bash
docker inspect <npm-container> | grep Gateway
```

#### SSL Tab:

1. Click **SSL** tab
2. Select **"Request a new SSL Certificate"**
3. Check:
   - ✅ **Force SSL** - Redirect HTTP to HTTPS
   - ✅ **HTTP/2 Support** - Better performance
   - ✅ **HSTS Enabled** - Security
   - ✅ **HSTS Subdomains** - Include subdomains
4. Enter **Email**: Your email for Let's Encrypt notifications
5. Click **"Save"**

**Wait 1-2 minutes** for Let's Encrypt to issue the certificate.

#### Advanced Tab (Optional but Recommended):

Paste this configuration:

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
    proxy_pass http://127.0.0.1:8888;
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
    proxy_pass http://127.0.0.1:8888/health;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

**Important:** If NPM is in Docker, replace `127.0.0.1` with the Docker gateway IP (usually `172.19.0.1`).

### Step 4: Verify Configuration

#### Test Health Endpoint:
```bash
curl https://mcp.ziksaka.com/health
# Expected: {"status":"healthy","service":"obsidian-mcp-server"}
```

#### Test MCP Endpoint:
```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
     -H "Content-Type: application/json" \
     -X POST https://mcp.ziksaka.com/mcp \
     -d '{"jsonrpc":"2.0","method":"ping","id":1}'
```

## 🔧 Troubleshooting

### DNS Not Resolving:
- Wait 5-10 minutes for DNS propagation
- Check DNS records are correct
- Verify A record points to `148.230.124.28`

### SSL Certificate Issues:
- Ensure DNS is resolving correctly first
- Check ports 80 and 443 are open
- Wait a few minutes for Let's Encrypt
- Check NPM logs for errors

### Connection Refused:
- Verify MCP server is running: `systemctl --user status obsidian-mcp`
- Check NPM forward hostname/IP is correct
- If NPM in Docker, use Docker gateway IP instead of 127.0.0.1

### 502 Bad Gateway:
- Check MCP server is accessible: `curl http://127.0.0.1:8888/health`
- Verify forward port is `8888`
- Check NPM logs

## 📝 Summary

Once configured:
- **Public URL**: `https://mcp.ziksaka.com/mcp`
- **Health Check**: `https://mcp.ziksaka.com/health`
- **Authentication**: Bearer token required (same API key from `.env`)

## 🧪 Quick Test Script

Save this as `test-external-access.sh`:

```bash
#!/bin/bash
API_KEY=$(grep MCP_API_KEY /home/franklinchris/obsidian-mcp-server/.env | cut -d'=' -f2)

echo "Testing external access..."
echo ""

echo "1. Health check:"
curl -s https://mcp.ziksaka.com/health | python3 -m json.tool
echo ""

echo "2. MCP ping:"
curl -s -H "Authorization: Bearer $API_KEY" \
     -H "Content-Type: application/json" \
     -X POST https://mcp.ziksaka.com/mcp \
     -d '{"jsonrpc":"2.0","method":"ping","id":1}' | python3 -m json.tool
```

Make it executable:
```bash
chmod +x test-external-access.sh
./test-external-access.sh
```


