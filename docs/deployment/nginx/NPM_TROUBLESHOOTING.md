# NPM 502 Bad Gateway Troubleshooting

## Issue
NPM is returning 502 Bad Gateway when trying to reach `172.17.0.1:8888`

## Possible Solutions

### Solution 1: Use host.docker.internal (Recommended)

If NPM is running in Docker, try using `host.docker.internal` instead:

1. In NPM, edit your Proxy Host
2. Change **Forward Hostname/IP** from `172.17.0.1` to `host.docker.internal`
3. Keep port `8888`
4. Save and test

### Solution 2: Use Docker Gateway IP

Find the correct Docker gateway IP:

```bash
# Find NPM container
docker ps | grep nginx-proxy-manager

# Get gateway IP
docker inspect <npm-container-id> | grep Gateway
```

Then use that IP in NPM's Forward Hostname/IP field.

### Solution 3: Change MCP Server to Listen on All Interfaces

If the above don't work, you can make the MCP server accessible from Docker:

1. **Edit .env file:**
   ```bash
   cd /home/franklinchris/obsidian-mcp-server
   # Change MCP_HOST from 127.0.0.1 to 0.0.0.0
   sed -i 's/MCP_HOST=127.0.0.1/MCP_HOST=0.0.0.0/' .env
   ```

2. **Restart service:**
   ```bash
   systemctl --user restart obsidian-mcp.service
   ```

3. **Update NPM Forward Hostname/IP** to `172.17.0.1` (or your Docker gateway IP)

4. **Test:**
   ```bash
   curl http://172.17.0.1:8888/health
   ```

### Solution 4: Use Docker Network Mode

If NPM and MCP server need better networking, you could:
- Run MCP server in Docker (more complex)
- Use Docker network bridge mode
- Use host networking mode for NPM

## Quick Test Commands

```bash
# Test from host
curl http://127.0.0.1:8888/health

# Test from Docker network perspective
curl http://172.17.0.1:8888/health

# Check Docker gateway
ip addr show docker0 | grep inet

# Check MCP server is listening
netstat -tlnp | grep 8888
```

## Recommended Fix

Try Solution 1 first (`host.docker.internal`), as it's the simplest and most reliable.

