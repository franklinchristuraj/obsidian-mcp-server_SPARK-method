"""Filesystem paths for MCP App HTML bundles."""
from __future__ import annotations

from pathlib import Path

# repo_root/src/apps/paths.py → repo_root
REPO_ROOT = Path(__file__).resolve().parents[2]
APPS_DIST_DIR = REPO_ROOT / "apps" / "dist"

UI_MIME_TYPE = "text/html;profile=mcp-app"
UI_SCHEME = "ui"
UI_AUTHORITY = "ziksaka"

# Restrictive CSP: no network from the iframe.
DEFAULT_UI_CSP = {
    "connectDomains": [],
    "resourceDomains": [],
    "frameDomains": [],
    "baseUriDomains": [],
}


def ui_uri(app_name: str) -> str:
    """Build ui://ziksaka/{app_name}."""
    return f"{UI_SCHEME}://{UI_AUTHORITY}/{app_name.strip('/')}"


def dist_html_path(app_name: str) -> Path:
    """Path to the single-file HTML bundle for an app."""
    return APPS_DIST_DIR / f"{app_name}.html"
