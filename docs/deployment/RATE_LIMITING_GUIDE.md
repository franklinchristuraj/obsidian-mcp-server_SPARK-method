# Rate Limiting Configuration Explained

## Rate Limiting Zones

### 1. MCP Endpoint Rate Limit
```nginx
limit_req_zone $binary_remote_addr zone=mcp_limit:10m rate=10r/s;
```
- **Zone**: `mcp_limit` (10MB memory)
- **Rate**: 10 requests per second per IP
- **Burst**: 20 requests allowed (burst buffer)
- **Applied to**: `/mcp` and `/` endpoints

### 2. Health Check Rate Limit
```nginx
limit_req_zone $binary_remote_addr zone=health_limit:10m rate=30r/s;
```
- **Zone**: `health_limit` (10MB memory)
- **Rate**: 30 requests per second per IP
- **Burst**: 50 requests allowed
- **Applied to**: `/health` endpoint

### 3. Authentication Rate Limit (Optional)
```nginx
limit_req_zone $binary_remote_addr zone=auth_limit:10m rate=5r/m;
```
- **Zone**: `auth_limit` (10MB memory)
- **Rate**: 5 requests per minute per IP
- **Use case**: Protect against brute force on auth endpoints

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
    -X POST -d '{"jsonrpc":"2.0","method":"ping","id":'$i'}'
done
```

## Security Headers Added

- **X-Frame-Options**: Prevents clickjacking
- **X-Content-Type-Options**: Prevents MIME type sniffing
- **X-XSS-Protection**: Enables XSS filtering
- **Referrer-Policy**: Controls referrer information

## Notes

- Rate limiting is per IP address (`$binary_remote_addr`)
- Burst allows temporary spikes but prevents sustained abuse
- 429 errors will be returned when limit exceeded
- Health checks have more lenient limits (30/sec vs 10/sec)

