# Ziksaka MCP Apps

Frontend for MCP Apps (`ui://ziksaka/...`).

- `packages/tokens` — Frank About AI CSS custom properties
- `packages/shell/bridge.js` — host bridge (postMessage JSON-RPC, SEP-1865)
- `dist/*.html` — single-file bundles served by `resources/read`

Python serves these files via `src/apps/registry.py`.

## Editing the bridge

`bridge.js` is the source of truth. Each bundle carries a generated copy
between `<!-- shell:bridge:start -->` and `<!-- shell:bridge:end -->`. After
editing it, re-inline it into every bundle:

```bash
python3 scripts/build_apps.py           # rewrite bundles
python3 scripts/build_apps.py --check   # CI gate: fail if drifted
```

## Lifecycle contract

The view MUST send `ui/notifications/initialized` after `ui/initialize`
resolves. Hosts are forbidden from sending `ui/notifications/tool-input` or
`ui/notifications/tool-result` before they see it, so skipping the
notification renders every app permanently blank.

The view SHOULD also emit `ui/notifications/size-changed`, or the host has no
way to size the iframe.

Both are covered by the host simulator:

```bash
node tests/shell/bridge_harness.mjs apps/dist/prep-card.html
pytest tests/test_mcp_apps_shell.py
```

## Local preview

Render a bundle against real vault data in a simulated host, with a live
message trace, without needing a Claude host:

```bash
export OBSIDIAN_VAULT_PATH=~/Documents/franklin-vault
python3 scripts/preview_app.py --list
python3 scripts/preview_app.py --app prep-card --open
python3 scripts/preview_app.py --app snapshot-entry --screenshot /tmp/shot.png
python3 scripts/preview_app.py --app prep-card --args '{"entity":"roche","scope":"work"}'
```

The preview host answers `ui/initialize` and pushes tool data, but cannot
proxy `tools/call` back to the server; interactive writes return a
"not supported in preview" error by design.
