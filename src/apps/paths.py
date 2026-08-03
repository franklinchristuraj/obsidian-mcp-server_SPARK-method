"""Filesystem paths for MCP App HTML bundles."""
from __future__ import annotations

import hashlib
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


def base_ui_uri(app_name: str) -> str:
    """Build the unversioned ui://ziksaka/{app_name}."""
    return f"{UI_SCHEME}://{UI_AUTHORITY}/{app_name.strip('/')}"


def bundle_version(app_name: str) -> str:
    """Short content hash of the bundle, used to cache-bust the UI resource URI.

    Hosts cache UI resources by URI, so a redeployed bundle at an unchanged URI
    keeps rendering the stale HTML. Deriving the suffix from the file contents
    means the URI changes exactly when the bundle does.
    """
    path = dist_html_path(app_name)
    if not path.is_file():
        return "0"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest[:12]


def ui_uri(app_name: str, versioned: bool = True) -> str:
    """Build ui://ziksaka/{app_name}@{content-hash}."""
    base = base_ui_uri(app_name)
    if not versioned:
        return base
    return f"{base}@{bundle_version(app_name)}"


def split_ui_uri(uri: str) -> tuple:
    """Split a ui:// URI into (app_name, version). Version is None when absent."""
    prefix = f"{UI_SCHEME}://{UI_AUTHORITY}/"
    if not uri.startswith(prefix):
        raise ValueError(f"Not a Ziksaka UI resource: {uri}")
    remainder = uri[len(prefix) :].strip("/")
    app_name, sep, version = remainder.partition("@")
    return app_name, (version if sep else None)


def dist_html_path(app_name: str) -> Path:
    """Path to the single-file HTML bundle for an app."""
    return APPS_DIST_DIR / f"{app_name}.html"
