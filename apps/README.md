# Ziksaka MCP Apps

Frontend for MCP Apps (`ui://ziksaka/...`).

- `packages/tokens` — Frank About AI CSS custom properties
- `packages/shell` — host bridge (postMessage JSON-RPC)
- `dist/*.html` — single-file bundles served by `resources/read`

Python serves these files via `src/apps/registry.py`. Rebuild check:

```bash
npm run build --prefix apps
# or
python3 scripts/build_apps.py
```
