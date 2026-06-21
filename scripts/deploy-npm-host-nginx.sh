#!/usr/bin/env bash
# Wire host nginx :80 → Nginx Proxy Manager (host :8085) so NPM can own :443 for TLS.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${REPO_ROOT}/docs/deployment/nginx/mcp.ziksaka.com.host-nginx.conf"
DEST="/etc/nginx/sites-available/npm-http-proxy.conf"
ENABLED="/etc/nginx/sites-enabled/npm-http-proxy.conf"
COACH_SITE="/etc/nginx/sites-enabled/coach-api.ziksaka.com"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo: sudo $0"
  exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -qx nginx-proxy-manager; then
  echo "nginx-proxy-manager container is not running. Start it first."
  exit 1
fi

if ! ss -tln | grep -q ':8085 '; then
  echo "NPM is not listening on host port 8085 (map 8085:80)."
  exit 1
fi

cp "$SRC" "$DEST"
ln -sf "$DEST" "$ENABLED"

# coach-api is already defined in NPM; avoid duplicate server_name on host :80
if [[ -e "$COACH_SITE" ]]; then
  echo "Disabling host-only coach-api site (NPM proxy_host 7 handles it)."
  rm -f "$COACH_SITE"
fi

nginx -t
systemctl reload nginx
echo "Done. Test: curl -sS https://mcp.ziksaka.com/health"
