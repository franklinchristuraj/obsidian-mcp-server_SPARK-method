"""Guards on the MCP Apps view shell (bridge lifecycle + bundle sync)."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "apps" / "dist"
HARNESS = ROOT / "tests" / "shell" / "bridge_harness.mjs"
BUNDLES = sorted(DIST.glob("*.html"))


def test_bundles_exist():
    assert BUNDLES, f"no UI bundles under {DIST}"


def test_bundles_in_sync_with_bridge_source():
    """apps/dist/*.html must carry the current apps/packages/shell/bridge.js."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_apps.py"), "--check"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("bundle", BUNDLES, ids=lambda p: p.name)
def test_bridge_completes_host_lifecycle(bundle: Path):
    """Hosts must not send tool data before ui/notifications/initialized."""
    if shutil.which("node") is None:
        pytest.skip("node not available")
    result = subprocess.run(
        ["node", str(HARNESS), str(bundle)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
