# Rate Limiting Configuration Explained

## No sticky sessions

After the 2026-07-28 dual-compat upgrade, MCP requests are self-describing.
Nginx does **not** need `ip_hash`, sticky cookies, or session affinity.
Any backend instance can serve any request (keep `workers=1` until the
SQLite task store is shared across processes).

## Rate Limiting Zones

### 1. Default MCP Endpoint Rate Limit (IP)
```nginx
limit_req_zone $binary_remote_addr zone=mcp_limit:10m rate=10r/s;
```
- **Zone**: `mcp_limit` (10MB memory)
- **Rate**: 10 requests per second per IP
- **Burst**: 20 requests allowed (burst buffer)
- **Applied to**: `/mcp` and `/` endpoints

### 2. Tool-aware limits via `Mcp-Name` (recommended)

Modern Streamable HTTP clients send `Mcp-Method` and `Mcp-Name` headers
(SEP-2243). Gateways can rate-limit without parsing JSON bodies:

```nginx
# Map missing/empty Mcp-Name to "other"
map $http_mcp_name $mcp_tool_bucket {
    default           $http_mcp_name;
    ""                "other";
}

# Loose tools (catalog / health)
limit_req_zone $binary_remote_addr zone=mcp_loose:10m rate=30r/s;

# Strict tools (writes / heavy vault work)
limit_req_zone $binary_remote_addr zone=mcp_strict:10m rate=2r/s;

# Example location fragments:
# if ($http_mcp_name ~* "^(ping|workspaces|server/discover)$") {
#     limit_req zone=mcp_loose burst=50 nodelay;
# }
# if ($http_mcp_name ~* "^(delete_note|lint_vault|debrief_submit)$") {
#     limit_req zone=mcp_strict burst=5 nodelay;
# }
```

**Loose:** `ping`, `workspaces`, `tools/list`, `server/discover`  
**Strict:** `delete_note`, `lint_vault`, `debrief_submit`

### 3. Health Check Rate Limit
```nginx
limit_req_zone $binary_remote_addr zone=health_limit:10m rate=30r/s;
```
- **Zone**: `health_limit` (10MB memory)
- **Rate**: 30 requests per second per IP
- **Burst**: 50 requests allowed
- **Applied to**: `/health` endpoint

### 4. Authentication Rate Limit (Optional)
```nginx
limit_req_zone $binary_remote_addr zone=auth_limit:10m rate=5r/m;
```
- **Zone**: `auth_limit` (10MB memory)
- **Rate**: 5 requests per minute per IP
- **Use case**: Protect against brute force on auth endpoints

## Proxy timeouts (Tasks vs sync)

With the Tasks extension, heavy tools (`lint_vault`, `build_context`,
`impact_rollup`, `graph_health`, `get_dossier`) return in ~1s when the
client advertises `io.modelcontextprotocol/tasks`. Prefer **60s**
`proxy_read_timeout` for normal POSTs.

Keep a longer timeout (e.g. 3600s) only if you still serve legacy clients
that run those tools synchronously without Tasks support, or for the
legacy `GET /mcp` keepalive channel.

```nginx
proxy_read_timeout 60s;
proxy_send_timeout 60s;
# Legacy SSE keepalive (GET /mcp) may still need longer if kept enabled:
# proxy_read_timeout 3600s;
```

## Rate Limit Settings Explained

- **rate=10r/s**: Maximum 10 requests per second per IP
- **burst=20**: Allows burst of 20 requests before rate limiting kicks in
- **nodelay**: Applies rate limit immediately (no queuing)
- **limit_req_status 429**: Returns HTTP 429 (Too Many Requests) when limit exceeded

## Adjusting Rate Limits

### For Higher Traffic:
```nginx
limit_req_zone $binary_remote_addr zone=mcp_limit:10m rate=50r/s;
limit_req zone=mcp_limit burst=100 nodelay;
```

### For Stricter Limits:
```nginx
limit_req_zone $binary_remote_addr zone=mcp_limit:10m rate=5r/s;
limit_req zone=mcp_limit burst=10 nodelay;
```

### For API Key-based Rate Limiting:
If you want to limit by API key instead of IP:
```nginx
limit_req_zone $http_authorization zone=api_limit:10m rate=100r/s;
```

## Testing Rate Limits

```bash
# Test rate limiting (should get 429 after exceeding limit)
for i in {1..25}; do
  curl -k https://mcp.ziksaka.com/mcp \
    -H "Authorization: Bearer YOUR_API_KEY" \
    -H "Content-Type: application/json" \
    -H "Mcp-Protocol-Version: 2026-07-28" \
    -H "Mcp-Method: ping" \
    -X POST -d '{"jsonrpc":"2.0","method":"ping","id":'$i'}'
done
```

## Security Headers Added

- **X-Frame-Options**: Prevents clickjacking
- **X-Content-Type-Options**: Prevents MIME type sniffing
- **X-XSS-Protection**: Enables XSS filtering
- **Referrer-Policy**: Controls referrer information

## Notes

- Default rate limiting is per IP address (`$binary_remote_addr`)
- Prefer `Mcp-Name` / `Mcp-Method` zones once modern clients are common
- Burst allows temporary spikes but prevents sustained abuse
- 429 errors will be returned when limit exceeded
- Health checks have more lenient limits (30/sec vs 10/sec)
