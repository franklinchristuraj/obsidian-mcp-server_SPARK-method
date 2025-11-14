# External Access Guide for Obsidian MCP Server

## ⚠️ Security Warning

**DO NOT expose the MCP server directly to the internet without proper security measures!**

The server uses API key authentication, but you should still:
- Use HTTPS (not HTTP)
- Use a reverse proxy (recommended)
- Consider firewall rules
- Monitor access logs
- Use strong API keys

## 🎯 Recommended: Use Reverse Proxy (Nginx Proxy Manager)

### Why Use a Reverse Proxy?

✅ **HTTPS/SSL encryption** - Secure connections  
✅ **Domain name** - Easier than IP addresses  
✅ **Rate limiting** - Protection against abuse  
✅ **DDoS protection** - Built-in security features  
✅ **SSL certificates** - Automatic Let's Encrypt  
✅ **Keep server on localhost** - More secure  

### Setup Steps

#### Option 1: Nginx Proxy Manager (Recommended)

1. **Keep server on localhost** (current setup is correct):
   ```bash
   # .env file should have:
   MCP_HOST=127.0.0.1
   MCP_PORT=8888
   ```

2. **Configure Nginx Proxy Manager:**
   - Access NPM at `http://your-ip:81` or your domain
   - Add new Proxy Host:
     - **Domain**: `mcp.yourdomain.com` (or use your IP with dynamic DNS)
     - **Scheme**: `http`
     - **Forward Hostname/IP**: `127.0.0.1` (if NPM on same server) or `172.19.0.1` (if NPM in Docker)
     - **Forward Port**: `8888`
     - **Websockets**: ✅ Enabled
     - **Block Common Exploits**: ✅ Enabled
   
3. **SSL Configuration:**
   - Request SSL certificate (Let's Encrypt)
   - Force SSL: ✅ Enabled
   - HTTP/2: ✅ Enabled

4. **Access via HTTPS:**
   ```
   https://mcp.yourdomain.com/mcp
   ```

#### Option 2: Direct IP Exposure (Not Recommended)

**⚠️ Only use if you understand the security risks!**

1. **Change server to listen on all interfaces:**
   ```bash
   # Edit .env file
   MCP_HOST=0.0.0.0  # Listen on all interfaces
   MCP_PORT=8888
   ```

2. **Restart service:**
   ```bash
   systemctl --user restart obsidian-mcp.service
   ```

3. **Configure firewall (if using ufw):**
   ```bash
   sudo ufw allow 8888/tcp
   ```

4. **Access via IP:**
   ```
   http://148.230.124.28:8888/mcp
   ```

**⚠️ Security Risks:**
- ❌ No HTTPS encryption (traffic is plain text)
- ❌ Exposed to internet attacks
- ❌ No rate limiting
- ❌ Harder to manage SSL certificates
- ❌ IP address can change

## 🔒 Security Best Practices

### 1. Use Strong API Keys
```bash
# Generate a secure API key
openssl rand -hex 32
```

### 2. Enable Firewall Rules
```bash
# Only allow specific IPs (if possible)
sudo ufw allow from TRUSTED_IP to any port 8888

# Or use fail2ban for brute force protection
```

### 3. Monitor Access Logs
```bash
# View access logs
journalctl --user -u obsidian-mcp.service -f

# Or check Nginx Proxy Manager logs
```

### 4. Use Domain Name Instead of IP
- Set up dynamic DNS if IP changes
- Use a subdomain (e.g., `mcp.yourdomain.com`)
- Easier to manage SSL certificates

## 📋 Quick Setup Checklist

### For Nginx Proxy Manager:
- [ ] Server running on `127.0.0.1:8888`
- [ ] Nginx Proxy Manager accessible
- [ ] Domain/subdomain configured
- [ ] Proxy host created in NPM
- [ ] SSL certificate obtained
- [ ] Test HTTPS connection
- [ ] Verify API key authentication works

### For Direct IP:
- [ ] Changed `MCP_HOST=0.0.0.0`
- [ ] Restarted service
- [ ] Opened firewall port
- [ ] Test HTTP connection
- [ ] Verify API key authentication works
- [ ] Consider setting up HTTPS later

## 🧪 Testing External Access

### Test with curl:
```bash
# Via domain (HTTPS)
curl -H "Authorization: Bearer YOUR_API_KEY" \
     -H "Content-Type: application/json" \
     -X POST https://mcp.yourdomain.com/mcp \
     -d '{"jsonrpc":"2.0","method":"ping","id":1}'

# Via IP (HTTP - not recommended)
curl -H "Authorization: Bearer YOUR_API_KEY" \
     -H "Content-Type: application/json" \
     -X POST http://148.230.124.28:8888/mcp \
     -d '{"jsonrpc":"2.0","method":"ping","id":1}'
```

## 🆘 Troubleshooting

### Can't access externally:
1. Check firewall: `sudo ufw status`
2. Check server is listening: `netstat -tlnp | grep 8888`
3. Check Nginx Proxy Manager logs
4. Verify domain DNS points to your IP

### SSL certificate issues:
1. Check domain DNS is correct
2. Ensure ports 80 and 443 are open
3. Wait a few minutes for Let's Encrypt

### Connection refused:
1. Verify server is running: `systemctl --user status obsidian-mcp`
2. Check host binding: `netstat -tlnp | grep 8888`
3. If using NPM, check forward hostname/IP is correct

## 📝 Summary

**Recommended Approach:**
1. ✅ Keep server on `127.0.0.1:8888` (localhost)
2. ✅ Use Nginx Proxy Manager as reverse proxy
3. ✅ Use domain name with SSL certificate
4. ✅ Access via `https://mcp.yourdomain.com/mcp`

**Alternative (Less Secure):**
1. ⚠️ Change to `0.0.0.0:8888` (all interfaces)
2. ⚠️ Open firewall port 8888
3. ⚠️ Access via `http://148.230.124.28:8888/mcp`
4. ⚠️ Consider adding HTTPS later

