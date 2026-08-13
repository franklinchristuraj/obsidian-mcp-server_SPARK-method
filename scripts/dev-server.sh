#!/usr/bin/env bash
# Local dev manager for the Obsidian MCP server (macOS).
#
# Usage:
#   scripts/dev-server.sh setup     # one-time: create venv, install deps, seed .env
#   scripts/dev-server.sh start     # start server in background (idempotent)
#   scripts/dev-server.sh stop      # stop the background server
#   scripts/dev-server.sh restart
#   scripts/dev-server.sh status
#   scripts/dev-server.sh logs      # tail the log
#
# Wired to Claude Code SessionStart/SessionEnd hooks so it starts when you open
# the project and stops when the session ends. All commands are safe to re-run.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VENV="$ROOT/.venv"
PY="$VENV/bin/python"
PID_FILE="$ROOT/.dev-server.pid"
LOG_FILE="$ROOT/dev-server.log"

# Resolve the port the server will actually bind to, mirroring
# main_production.py's precedence: exported env wins, then .env.production,
# then .env. No default — a guessed port would make every command here
# (status, stop, the port_pid guard) silently target the wrong listener.
env_file_port() {
  [ -f "$1" ] || return 1
  local v
  v="$(grep -E '^[[:space:]]*MCP_PORT=' "$1" 2>/dev/null | tail -1 | cut -d= -f2- \
       | tr -d '"'"'"'[:space:]')"
  [ -n "$v" ] && echo "$v"
}

PORT="${MCP_PORT:-$(env_file_port "$ROOT/.env.production" || env_file_port "$ROOT/.env" || true)}"

# Validated lazily rather than at load time: `setup` is what creates .env in
# the first place, so a hard check here would deadlock a fresh clone against
# an error message telling it to run `setup`.
require_port() {
  if [ -z "${PORT:-}" ]; then
    echo "❌ MCP_PORT is not set in the environment, $ROOT/.env.production, or $ROOT/.env." >&2
    echo "   Refusing to guess a port. Run 'scripts/dev-server.sh setup' or copy .env.example (MCP_PORT=8000)." >&2
    exit 1
  fi
  if ! [ "$PORT" -eq "$PORT" ] 2>/dev/null; then
    echo "❌ MCP_PORT must be an integer, got '$PORT'." >&2
    exit 1
  fi
}

is_running() {
  [ -f "$PID_FILE" ] || return 1
  local pid; pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

port_pid() { lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null | head -1; }

find_python() {
  for c in \
    /opt/homebrew/opt/python@3.12/bin/python3.12 \
    python3.13 python3.12 python3.11 python3.10; do
    if command -v "$c" >/dev/null 2>&1; then echo "$c"; return 0; fi
  done
  return 1
}

setup() {
  if [ ! -x "$PY" ]; then
    local base; base="$(find_python)" || {
      echo "❌ Need Python >=3.10 (the 'mcp' package requires it). Try: brew install python@3.12" >&2
      return 1
    }
    echo "📦 Creating venv with $base ..."
    "$base" -m venv "$VENV" || return 1
  fi
  echo "📦 Installing dependencies ..."
  "$PY" -m pip install -q --upgrade pip >/dev/null
  "$PY" -m pip install -q -r "$ROOT/requirements.txt" || return 1
  if [ ! -f "$ROOT/.env" ] && [ -f "$ROOT/.env.example" ]; then
    cp "$ROOT/.env.example" "$ROOT/.env"
    echo "📝 Created .env from .env.example — fill in OBSIDIAN_API_KEY / vault path."
  fi
  echo "✅ Setup complete."
}

start() {
  if is_running; then
    echo "✅ MCP dev server already running (pid $(cat "$PID_FILE"))."
    return 0
  fi
  if [ -n "$(port_pid)" ]; then
    echo "ℹ️  Port $PORT already in use (pid $(port_pid)); leaving it alone."
    return 0
  fi
  if [ ! -x "$PY" ]; then
    echo "ℹ️  venv not set up yet — run: scripts/dev-server.sh setup"
    return 0
  fi
  echo "🚀 Starting MCP dev server on http://127.0.0.1:$PORT ..."
  nohup "$PY" "$ROOT/main_production.py" >>"$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"
  sleep 1
  if is_running; then
    echo "✅ Started (pid $(cat "$PID_FILE")). Logs: dev-server.log"
  else
    echo "❌ Failed to start — check dev-server.log" >&2
    rm -f "$PID_FILE"
    return 1
  fi
}

stop() {
  if is_running; then
    local pid; pid="$(cat "$PID_FILE")"
    echo "🛑 Stopping MCP dev server (pid $pid) ..."
    kill "$pid" 2>/dev/null || true
    for _ in 1 2 3 4 5 6; do is_running || break; sleep 0.3; done
    is_running && kill -9 "$pid" 2>/dev/null || true
    rm -f "$PID_FILE"
    echo "✅ Stopped."
  else
    rm -f "$PID_FILE"
    echo "ℹ️  Not running."
  fi
}

status() {
  if is_running; then
    echo "✅ Running (pid $(cat "$PID_FILE")) on http://127.0.0.1:$PORT"
  elif [ -n "$(port_pid)" ]; then
    echo "⚠️  Port $PORT held by pid $(port_pid) but no PID file (started outside this script)."
  else
    echo "⛔ Not running."
  fi
}

case "${1:-}" in
  setup)   setup ;;
  start)   require_port; start ;;
  stop)    require_port; stop ;;
  restart) require_port; stop; start ;;
  status)  require_port; status ;;
  logs)    tail -n 50 -f "$LOG_FILE" ;;
  *) echo "Usage: $0 {setup|start|stop|restart|status|logs}" >&2; exit 1 ;;
esac
