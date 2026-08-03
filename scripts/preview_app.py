#!/usr/bin/env python3
"""Render an MCP App bundle in a simulated host for local preview.

Builds a standalone HTML page that plays the host side of SEP-1865: it answers
ui/initialize, waits for ui/notifications/initialized, then pushes tool-input
and tool-result, and proxies tools/call back to the live server tools.

Usage:
    python scripts/preview_app.py --app snapshot-entry --open
    python scripts/preview_app.py --list
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import webbrowser
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DIST = ROOT / "apps" / "dist"

# app slug -> (tool name, default arguments)
APPS: Dict[str, tuple[str, Dict[str, Any]]] = {
    "smoke": ("mcp_apps_smoke", {}),
    "prep-card": ("prep_card", {"entity": "4flow", "scope": "work"}),
    "lint-queue": ("lint_queue", {"scope": "work"}),
    "snapshot-entry": ("snapshot_grid", {"scope": "work"}),
    "debrief-form": ("debrief_form", {"customer": "4flow", "scope": "work"}),
    "triage-board": ("triage_board", {"limit": 50}),
}


async def run_tool(tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
    from src.apps.registry import execute_app_tool

    result = await execute_app_tool(tool, args)
    if hasattr(result, "model_dump"):
        result = result.model_dump()
    if isinstance(result, dict):
        return result
    return {"content": [{"type": "text", "text": str(result)}]}


HOST_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Ziksaka app preview — __APP__</title>
<style>
  body {
    margin: 0;
    font: 13px/1.5 ui-monospace, monospace;
    background: #1C1B19;
    color: #FBF8F5;
    display: grid;
    grid-template-columns: 1fr 360px;
    height: 100vh;
  }
  .stage { padding: 16px; overflow: auto; }
  .bar {
    font-size: 11px;
    letter-spacing: .1em;
    text-transform: uppercase;
    color: #6EB0B6;
    margin-bottom: 10px;
  }
  iframe {
    width: 100%;
    border: 1px solid #0E7C86;
    border-radius: 8px;
    background: #FBF8F5;
    display: block;
  }
  .log { border-left: 1px solid #333; padding: 16px; overflow: auto; font-size: 11px; }
  .log div { padding: 2px 0; border-bottom: 1px solid #262523; white-space: pre-wrap; }
  .in { color: #6EB0B6; }
  .out { color: #DD8E74; }
</style>
</head>
<body>
<div class="stage">
  <div class="bar">Simulated host · __APP__ · tool: __TOOL__</div>
  <iframe id="view" srcdoc="__SRCDOC__" sandbox="allow-scripts"></iframe>
</div>
<div class="log"><div class="bar">Message trace</div><div id="log"></div></div>
<script>
const TOOL_RESULT = __RESULT__;
const TOOL_ARGS = __ARGS__;
const view = document.getElementById("view");
const logEl = document.getElementById("log");
function log(dir, msg) {
  const d = document.createElement("div");
  d.className = dir;
  d.textContent = (dir === "in" ? "\\u2190 " : "\\u2192 ") + (msg.method || "response id=" + msg.id);
  logEl.appendChild(d);
}
function post(msg) { log("out", msg); view.contentWindow.postMessage(msg, "*"); }

window.addEventListener("message", (ev) => {
  const msg = ev.data;
  if (!msg || msg.jsonrpc !== "2.0") return;
  log("in", msg);

  if (msg.method === "ui/initialize") {
    post({ jsonrpc: "2.0", id: msg.id, result: {
      protocolVersion: "2026-01-26",
      hostInfo: { name: "ziksaka-preview", version: "1.0.0" },
      capabilities: { serverTools: {}, openLinks: {} },
      hostContext: { theme: "light", displayMode: "inline", availableDisplayModes: ["inline", "fullscreen"] }
    }});
    return;
  }
  // Spec: send tool data only after the view reports it is initialized.
  if (msg.method === "ui/notifications/initialized") {
    post({ jsonrpc: "2.0", method: "ui/notifications/tool-input", params: { arguments: TOOL_ARGS } });
    post({ jsonrpc: "2.0", method: "ui/notifications/tool-result", params: TOOL_RESULT });
    return;
  }
  if (msg.method === "ui/notifications/size-changed") {
    view.style.height = Math.max(160, msg.params.height + 8) + "px";
    return;
  }
  if (msg.id != null && msg.method) {
    // Preview host cannot reach the server; report instead of hanging.
    post({ jsonrpc: "2.0", id: msg.id, error: { code: -32601, message: "not supported in preview: " + msg.method } });
  }
});
</script>
</body>
</html>
"""


def build_page(app: str, result: Dict[str, Any], args: Dict[str, Any]) -> str:
    bundle = (DIST / f"{app}.html").read_text()
    srcdoc = (
        bundle.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
    )
    tool = APPS[app][0]
    return (
        HOST_TEMPLATE.replace("__SRCDOC__", srcdoc)
        .replace("__RESULT__", json.dumps(result))
        .replace("__ARGS__", json.dumps(args))
        .replace("__APP__", app)
        .replace("__TOOL__", tool)
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", choices=sorted(APPS), help="app slug to preview")
    parser.add_argument("--list", action="store_true", help="list app slugs")
    parser.add_argument("--args", help="JSON tool arguments override")
    parser.add_argument("--out", help="output HTML path")
    parser.add_argument("--open", action="store_true", help="open in browser")
    parser.add_argument("--screenshot", help="write a PNG using headless chromium")
    opts = parser.parse_args()

    if opts.list or not opts.app:
        for slug, (tool, args) in sorted(APPS.items()):
            print(f"{slug:16s} -> {tool} {json.dumps(args)}")
        return 0

    if not os.environ.get("OBSIDIAN_VAULT_PATH"):
        print("OBSIDIAN_VAULT_PATH is not set; tool data will be empty.", file=sys.stderr)

    tool, default_args = APPS[opts.app]
    args = json.loads(opts.args) if opts.args else default_args
    result = asyncio.run(run_tool(tool, args))

    out = Path(opts.out) if opts.out else Path(tempfile.gettempdir()) / f"ziksaka-{opts.app}.html"
    out.write_text(build_page(opts.app, result, args))
    print(f"preview: {out}")

    if opts.screenshot:
        candidates = [
            "Library/Caches/ms-playwright/chromium_headless_shell-*/"
            "chrome-headless-shell-*/chrome-headless-shell",
            "Library/Caches/ms-playwright/chromium-*/chrome-mac*/"
            "Chromium.app/Contents/MacOS/Chromium",
        ]
        shell = next(
            (p for pattern in candidates for p in sorted(Path.home().glob(pattern))),
            None,
        )
        if shell is None:
            print("headless chromium not found", file=sys.stderr)
            return 1
        subprocess.run(
            [
                str(shell),
                "--headless",
                "--disable-gpu",
                "--no-sandbox",
                "--hide-scrollbars",
                "--virtual-time-budget=3000",
                "--window-size=1280,900",
                f"--screenshot={opts.screenshot}",
                out.as_uri(),
            ],
            check=True,
            capture_output=True,
        )
        print(f"screenshot: {opts.screenshot}")

    if opts.open:
        webbrowser.open(out.as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
