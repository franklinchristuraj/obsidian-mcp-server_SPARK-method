# NPM port 80 conflict fix (2026-06-01)

## Problem

Host nginx owned port **80**, so `nginx-proxy-manager` could not start (`address already in use`). The container also lost its Docker network and could not resolve hostname `db`.

## Fix applied

1. Reconnected NPM to `nginx-proxy-manager_default` (same network as `npm-db`).
2. Recreated `nginx-proxy-manager` **without** host port `80:80`; instead **`8085:80`** so NPM HTTP (ACME + redirects) is on `127.0.0.1:8085`.
3. NPM still publishes **`443:443`** and **`81:81`**.

## Verify

```bash
curl -sS https://mcp.ziksaka.com/health
# {"status":"healthy","service":"obsidian-mcp-server"}
```

## Optional: HTTP on port 80 (redirect + ACME)

Host nginx still answers plain HTTP with 404 for `mcp.ziksaka.com` until you proxy port 80 to NPM:

```bash
sudo /home/franklinchris/obsidian-mcp-server/scripts/deploy-npm-host-nginx.sh
```

## Portainer stack

If you redeploy from Portainer, change port mapping from `80:80` to `8085:80` and keep `443:443`, `81:81`. Ensure the `app` service uses network `nginx-proxy-manager_default` with `db`.
