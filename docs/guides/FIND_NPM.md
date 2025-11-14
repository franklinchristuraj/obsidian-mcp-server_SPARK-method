# Finding Nginx Proxy Manager

## Current Status
- ✅ Portainer: Running on port 9443
- 🔍 Nginx Proxy Manager: Not found on common ports (81, 8080, 8181)
- 🔍 Port 8000: Unknown service (checking...)

## Options

### Option 1: NPM Already Running (Check Port 8000)
If NPM is on port 8000, access it at:
- `http://148.230.124.28:8000`
- Default login: `admin@example.com` / `changeme`

### Option 2: Install Nginx Proxy Manager via Portainer

Since you have Portainer, you can easily deploy NPM:

1. **Access Portainer**: `https://148.230.124.28:9443`

2. **Deploy NPM Stack**:
   - Go to **Stacks** → **Add Stack**
   - Name: `nginx-proxy-manager`
   - Paste this docker-compose:

```yaml
version: '3.8'
services:
  app:
    image: 'jc21/nginx-proxy-manager:latest'
    container_name: nginx-proxy-manager
    restart: unless-stopped
    ports:
      - '80:80'
      - '443:443'
      - '81:81'
    volumes:
      - ./data:/data
      - ./letsencrypt:/etc/letsencrypt
    environment:
      DB_MYSQL_HOST: "db"
      DB_MYSQL_PORT: 3306
      DB_MYSQL_USER: "npm"
      DB_MYSQL_PASSWORD: "npm"
      DB_MYSQL_NAME: "npm"
    depends_on:
      - db

  db:
    image: 'jc21/mariadb-aria:latest'
    container_name: npm-db
    restart: unless-stopped
    volumes:
      - ./data/mysql:/var/lib/mysql
    environment:
      MYSQL_ROOT_PASSWORD: 'npm'
      MYSQL_DATABASE: 'npm'
      MYSQL_USER: 'npm'
      MYSQL_PASSWORD: 'npm'
```

3. **Deploy** and wait for containers to start

4. **Access NPM**: `http://148.230.124.28:81`
   - Default login: `admin@example.com`
   - Default password: `changeme`

### Option 3: Use Portainer's Built-in Reverse Proxy

Portainer has some reverse proxy capabilities, but NPM is more feature-rich for this use case.

## Recommended: Use NPM

Nginx Proxy Manager is the best choice because:
- ✅ Easy SSL certificate management (Let's Encrypt)
- ✅ User-friendly web interface
- ✅ Built-in security features
- ✅ Perfect for exposing MCP server

## Next Steps

1. **Check if NPM is on port 8000**:
   ```bash
   curl http://localhost:8000
   ```

2. **If not found, deploy via Portainer** (Option 2 above)

3. **Once NPM is accessible, follow the setup guide**:
   - See `NPM_SETUP_INSTRUCTIONS.md` for detailed steps


