# Obsidian headless migration — 2026-07-08

Retired the Obsidian Electron/VNC container in favor of `obsidian-headless` sync
+ a filesystem-native MCP server. Full rationale and phased plan are in
[`PRD_revamp-filemcp_jul26`](../PRD_revamp-filemcp_jul26) at the repo root —
this doc is the after-the-fact record of what was actually done, what broke
along the way, and where everything lives now. The container, its bind-mounted
vault copy, and its compose file no longer exist on disk; this document is the
reference for their configuration.

## Before / after

**Before:** `lscr.io/linuxserver/obsidian` (KasmVNC: Xvfb + openbox + pulseaudio
+ nginx + selkies WebRTC), running 24/7 solely to keep the Local REST API
community plugin alive on port 27123, which the MCP server called over HTTP.
Cost: ~1.02-1.19 GiB RAM permanently committed, for a plugin endpoint.

**After:** two independent, minimal pieces:
1. `obsidian-headless` (official CLI, still open beta) — a systemd user
   service doing continuous bidirectional Obsidian Sync. ~18-50 MB RAM.
2. `obsidian-mcp-server`'s `ObsidianClient` reads/writes vault files directly
   on disk via a shared `VaultCorpus` — no REST, no bearer token, no
   dependency on any Obsidian process being alive.

Plus a piece the old architecture provided implicitly and now has to be
explicit: a staleness watchdog, since sync and API are no longer one process
that fails loudly together.

## Current canonical paths

- **Vault:** `/home/franklinchris/vaults/franklin-vault/` (631+ notes, ~18-20 MB).
  This is the *only* copy now — the old container bind-mount path
  (`/home/franklinchris/obsidian/config/franklin-vault/`, and the ~218 MB of
  Electron/KasmVNC profile cruft alongside it) was deleted after this
  migration was fully verified. See "Old path removal" below.
- **MCP server:** `/home/franklinchris/obsidian-mcp-server/`, systemd user
  unit `~/.config/systemd/user/obsidian-mcp.service`, port 8888, fronted
  publicly by `nginx-proxy-manager` at `https://mcp.ziksaka.com`.
- **Sync daemon:** systemd user unit
  `~/.config/systemd/user/obsidian-headless.service`, running
  `ob sync --continuous --path /home/franklinchris/vaults/franklin-vault`.
- **Sync state/logs:**
  `~/.config/obsidian-headless/sync/196016e0c256a2c3ef55e1e93a696e98/` —
  `state.db` (SQLite, the client's own sync state) and `sync.log` (per-line
  timestamped activity log; its mtime is the staleness signal, see below).
- **Backups:** git repo *inside* the vault itself (`.git`, `.gitignore`
  excludes `.trash/` and `.mcp-write.lock`), nightly auto-commit via cron.
  Baseline tarball: `~/franklin-vault-backup-20260708-2013.tar.gz`.
- **Watchdog:** `~/scripts/obsidian-sync-watchdog.sh`, cron every 5 min,
  alerts (log-only currently, no push channel wired up) to
  `~/scripts/obsidian-sync-watchdog-alerts.log`.

## Backups (Phase 0 / 0.5)

```
0 3 * * * /home/franklinchris/scripts/vault-backup-commit.sh >> /home/franklinchris/scripts/vault-backup.log 2>&1
```

`vault-backup-commit.sh` does `git add -A && git commit -m "auto: <iso timestamp>"`
inside the vault, no-op if nothing changed. **Bug found and fixed during this
migration:** it originally defaulted `VAULT_PATH` to the *old* container path;
fixed to default to the new canonical path. If this script is ever copied
elsewhere, check `VAULT_PATH` points at the live vault before trusting it.

## Sync setup (Phase 1)

`obsidian-headless@0.0.12` (npm global, `~/.npm-global/bin/ob`), logged in as
`christuraj.anto@gmail.com`, `sync-setup` run against the real remote vault
`franklin-vault` (id `196016e0c256a2c3ef55e1e93a696e98`, EU region) —
bidirectional mode, merge conflict strategy, device name `vps-headless`.

**Note:** the account's plan has a vault-count limit, so a disposable test
remote for a dry run (`ob sync-create-remote`) was not available. Sync-setup
was run directly against the real vault, mitigated by the Phase 0/0.5 backups
and the old path being left untouched until full verification.

### Gotcha: Node version

`ob` requires Node 22+. This box's system-installed `apt` Node is v18.19.1,
which lacks the `globalThis.crypto` API `obsidian-headless` needs — it
crashes hard (`ReferenceError: crypto is not defined`) under systemd's
minimal `PATH`, even though it works fine interactively (nvm's Node 22.23.1
is what's on the interactive shell's `PATH`). Fixed by pinning
`obsidian-headless.service`'s `Environment=PATH=...` to nvm's v22 bin dir
explicitly — **do not rely on the system Node for this service.**

### Gotcha: `:` / `[]` in filenames → infinite re-upload loop

`obsidian-headless` gets stuck re-uploading the same file every ~10s
("New file" → "Uploading" → "Upload complete", forever) for filenames
containing `:` or `[]`. Hit this on 3 real files/folders in the vault:
- `01_seeds/Insight: Human Judges in LLM Evaluation.md`
- `01_seeds/LLM Evaluation: Human Judges for Edge Cases.md`
- `work/[RAW FOLDER]/` (containing 2 files)

**Fix:** renamed to strip the offending characters (`:` → ` -`, drop `[]`).
Renaming only on one side isn't enough — each sync client (the new headless
path, and at the time, the still-live container on the old path) owns its own
local copy, so a rename on one side just gets partially reconciled: the other
side pulls the new name down as an *additional* file rather than replacing
its old-named copy, producing byte-identical duplicates. Both sides had to be
renamed/cleaned up manually. If a *new* file with special characters starts
looping in `sync.log`, this is the first thing to suspect.

### Running as a service (Phase 1c)

`~/.config/systemd/user/obsidian-headless.service`:
```ini
[Unit]
Description=Obsidian headless sync (obsidian-headless)
After=network.target
Wants=network.target

[Service]
Type=simple
WorkingDirectory=/home/franklinchris/vaults/franklin-vault
Environment="PATH=/home/franklinchris/.nvm/versions/node/v22.23.1/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/home/franklinchris/.npm-global/bin/ob sync --continuous --path /home/franklinchris/vaults/franklin-vault
Restart=always
RestartSec=10
StartLimitInterval=300
StartLimitBurst=5

StandardOutput=journal
StandardError=journal
SyslogIdentifier=obsidian-headless

[Install]
WantedBy=default.target
```

Verified: `kill -9` on the main PID → systemd restarts it within ~10s
(`RestartSec=10`), reconnects and re-syncs cleanly.

### Staleness watchdog

`ob sync-status` turned out to report only static config, not freshness —
contrary to what the PRD assumed going in. Freshness signal actually used:
`sync.log`'s mtime (it's touched on every sync tick, roughly every 30s).

`~/scripts/obsidian-sync-watchdog.sh` (cron `*/5 * * * *`):
- Alerts if `systemctl --user is-active obsidian-headless.service` isn't `active`.
- Alerts if `sync.log`'s mtime is more than 1800s (30 min) old.
- Appends to `~/scripts/obsidian-sync-watchdog-alerts.log`. No push
  notification channel wired up yet (ntfy/Slack/etc.) — deliberately deferred,
  log-only for now.
- Needs `XDG_RUNTIME_DIR=/run/user/1001` set explicitly (exported at the top
  of the script) for `systemctl --user` to work from cron's minimal environment.

Same freshness signal is also surfaced live via the MCP server's `ping` tool
(see below), so a stale vault is visible from inside an MCP conversation too,
not only from the cron alert log.

## Filesystem-native MCP server (Phase 2)

`src/vault_intelligence/corpus.py` (`VaultCorpus`) is now the single
read/write path, shared between `ObsidianClient` (CRUD tools) and
`VaultIntelligenceTools` (`resolve_entity`/`query_frontmatter`/`get_dossier`/
`lint_vault`/search) so a write via one is immediately visible to the other
through the same mtime cache.

- **Atomic writes:** temp file in the same directory + `os.replace()`.
- **Lost-update guard:** `write_note`/`append_note` accept an
  `expected_mtime`; if the on-disk mtime changed since it was read (e.g. a
  sync pull landed in between), raises `ConcurrentModificationError` instead
  of silently clobbering. `append_note` retries once (re-reads, re-appends)
  before giving up.
- **Deletes:** move to `<vault>/.trash/<scope>/...` instead of unlinking,
  with a timestamp suffix on name collisions.
- **Locking:** single coarse `fcntl.flock` on `<vault>/.mcp-write.lock`,
  reentrant per-`asyncio.Task` so multi-step tool flows (e.g. `create_event`)
  can hold it across their whole sequence.
- `ObsidianClient` dropped `httpx`/REST entirely for its own operations
  (still a `requirements.txt` dependency for unrelated diagnostic scripts),
  and dropped the unused `execute_command`/`search_notes` tools (confirmed no
  consumers).
- `get_stats()` gained a `sync: {configured, fresh, age_seconds}` field
  reading the same `sync.log` mtime signal as the watchdog. Initially this
  was dead code (nothing called `get_stats()`) — fixed by extending the
  `ping` MCP tool to report vault readability + this sync-freshness info, so
  it's actually reachable from a live MCP conversation.

Committed as `baf6348` on `obsidian-mcp-server` main (12 files,
+847/-1286 lines), pushed to
`git@github.com:franklinchristuraj/obsidian-mcp-server_SPARK-method.git`
(the repo was renamed on GitHub from `obsidian-mcp-server`; `origin` was
updated to the new URL).

### Verification performed

- Full test suite: 73 passing (1 pre-existing, unrelated failure —
  `test_resolve_entity_fuzzy_gojo`, confirmed present on `main` before this
  work via `git stash`, not a regression).
- Concurrency burst test (throwaway tmp vault, real corpus code): 20
  concurrent appends to the same note (no lost updates, no duplication), 50
  concurrent creates to different notes (no cross-talk), and a forced
  lost-update race (monkeypatched an external write to land exactly between
  the mtime read and the replace) — correctly retried and preserved the
  external writer's content instead of clobbering it.
- Live end-to-end against the actual running `obsidian-mcp.service`: full
  CRUD round-trip (`create_note` → `read_note` → `update_note` →
  `append_note` → `search` → `delete_note` landing in `.trash`), and a write
  via `create_note` immediately visible to `resolve_entity` (shared cache).
  **Note:** the running service had been up since before this work started
  (2026-07-07, pre-dating all these changes) and had to be restarted to
  actually load the new code/`.env` — it does not hot-reload.
- Manifest diff (path list) between old and new vault paths, repeated
  several times across the migration: always clean except expected
  artifacts (`.mcp-write.lock`, the renamed files above).
- Real phone-edit round-trip: an edit typed on the phone Obsidian app
  ("This one is good.") landed byte-for-byte in the vault via headless sync
  alone (confirmed via `git diff` in the vault's own repo), and the live MCP
  server's `read_note` returned it immediately with no restart needed.
- Crash recovery: `kill -9` on `obsidian-headless`'s PID → systemd
  auto-restarted within `RestartSec=10`, reconnected and resumed syncing
  cleanly.

## Decommission (Phase 3) — 2026-07-08

```
docker compose -f ~/compose/obsidian/docker-compose.yml down
```
removed the `obsidian` container and its bridge network (`obsidian_default`).

**Original `docker-compose.yml`** (preserved here verbatim since the file
itself has since been deleted — see "Old path removal"):
```yaml
version: '3.8'

services:
  obsidian:
    image: lscr.io/linuxserver/obsidian:latest
    container_name: obsidian
    environment:
      - PUID=1001
      - PGID=1001
      - TZ=Europe/Paris
      - CUSTOM_USER=franklinchris
      - PASSWORD=[REDACTED]  # was the KasmVNC login password for this container
    volumes:
      - /home/franklinchris/obsidian/config:/config
      - /home/franklinchris/obsidian/vaults:/vaults
    ports:
      - 3000:3000
      - 3001:3001
      - 27123:27123
    shm_size: "1gb"
    restart: unless-stopped
```
(`/home/franklinchris/obsidian/vaults` was an unused second bind mount —
always empty; the real vault content lived at
`/home/franklinchris/obsidian/config/franklin-vault/`.)

**Firewall:** ports 3000/3001/27123 needed **no manual iptables changes**.
This box runs bare iptables (no UFW), and Docker manages NAT/forward rules
per-container automatically via its own bridge network — removing the
container's network already deleted the DNAT rules that routed those ports
to it. Verified via `ss -tln` (nothing listening), direct connect attempts
(`Connection refused`), and `iptables -S` / `iptables -t nat -S` showing no
rules referencing those ports or that bridge anymore. `nginx-proxy-manager`
confirmed unaffected — its only remaining `proxy_host` row is
`mcp.ziksaka.com` (id 1); nothing else was ever routed to the removed ports.

**RAM:** system-wide usage dropped from a 2.3 GiB baseline to ~1.2 GiB used
(of 7.8 GiB total) — the ~1.19 GiB `obsidian` container fully reclaimed.
`obsidian-headless` costs ~18-50 MB in its place.

### Old path removal — 2026-07-08 (after this doc was written)

Per Franklin's explicit request, the old container bind-mount path
(`/home/franklinchris/obsidian/` — the vault copy at `config/franklin-vault/`
plus ~218 MB of Electron/KasmVNC/XDG profile cruft in `config/.cache`,
`config/.config`, `config/.local`, etc., and the always-empty `vaults/` bind
mount) and the archived compose file (both the working copy at
`~/compose/obsidian/docker-compose.yml` and the safety copy at
`~/archives/obsidian-compose-archived-20260708/`) were deleted outright,
rather than kept for a release-cycle grace period as the PRD originally
suggested. This document (plus the compose YAML preserved above) is now the
sole reference for that configuration — there is no copy of the old vault
path or compose file left on disk. The current vault at
`/home/franklinchris/vaults/franklin-vault/` is fully backed up independently
(nightly git commits + the 2026-07-08 baseline tarball), so this carries no
data-loss risk.

## Open items (deliberately deferred)

- **Push notification channel for the watchdog** — currently log-only
  (`~/scripts/obsidian-sync-watchdog-alerts.log`). Franklin chose not to wire
  up ntfy/Slack/email yet; revisit if the log-only alert is ever missed.
- The compose file for `nginx-proxy-manager`/`npm-db` at
  `~/compose/npm/docker-compose.yml` has a known port-mapping mismatch
  (says `80:80`, actually runs `8085:80`) — unrelated to this migration, not
  touched, documented in memory only.
