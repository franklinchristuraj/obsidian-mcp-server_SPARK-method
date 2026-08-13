#!/usr/bin/env bash
# Health-check the local MCP server and restart it if it is down.
#
# Driven by a launchd StartInterval timer (com.frank.mcp-local-watchdog)
# rather than by KeepAlive on the server job itself: on this machine launchd
# accepts KeepAlive/RunAtLoad on com.frank.mcp-local but never acts on them,
# so a killed server stays dead. An explicit `launchctl kickstart` does work,
# which is what this script drives.
#
# Usage: scripts/watchdog.sh [--once]
# Exit 0 when the server is up (or was recovered), 1 when it could not be.

set -uo pipefail

LABEL="com.frank.mcp-local"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Match the port the server actually binds: explicit env, then .env, then the
# uvicorn default in main_production.py.
env_port="$(grep -E '^MCP_PORT=' "$ROOT/.env" 2>/dev/null | tail -1 | cut -d= -f2 | tr -d '[:space:]')"
PORT="${MCP_PORT:-${env_port:-8888}}"
URL="http://127.0.0.1:${PORT}/health"

ts() { date "+%Y-%m-%dT%H:%M:%S%z"; }
healthy() { curl -fsS -m 5 "$URL" >/dev/null 2>&1; }

if healthy; then
  exit 0
fi

wait_healthy() {
  local tries="$1"
  while [ "$tries" -gt 0 ]; do
    sleep 2
    healthy && return 0
    tries=$((tries - 1))
  done
  return 1
}

echo "$(ts) DOWN: $URL did not respond — kickstarting $LABEL"
launchctl kickstart "gui/$(id -u)/${LABEL}" 2>&1 || true

if wait_healthy 5; then
  echo "$(ts) RECOVERED via launchctl: $URL responding"
  exit 0
fi

# cron runs outside the Aqua session, where addressing gui/<uid> can fail.
# Fall back to starting the server directly, detached from this shell.
echo "$(ts) kickstart did not take — starting detached"
cd "$ROOT" || exit 1
nohup "$ROOT/.venv/bin/python" "$ROOT/main_production.py" \
  >>"$HOME/Library/Logs/mcp-local.out.log" 2>&1 &
disown 2>/dev/null || true

if wait_healthy 10; then
  echo "$(ts) RECOVERED detached: $URL responding"
  exit 0
fi

echo "$(ts) FAILED: still down — see ~/Library/Logs/mcp-local.err.log"
exit 1
