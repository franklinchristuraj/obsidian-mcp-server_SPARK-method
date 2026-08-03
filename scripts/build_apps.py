#!/usr/bin/env python3
"""Assemble single-file MCP App HTML into apps/dist/.

Currently the committed dist/*.html bundles are the source of truth for the
server. Re-run the generator in-repo when editing apps (see apps/README.md).
This script verifies required bundles exist so CI can gate on them.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "apps" / "dist"
REQUIRED = (
    "smoke",
    "prep-card",
    "lint-queue",
    "snapshot-entry",
    "debrief-form",
    "triage-board",
)


def main() -> int:
    missing = [name for name in REQUIRED if not (DIST / f"{name}.html").is_file()]
    if missing:
        print(f"Missing UI bundles: {missing}", file=sys.stderr)
        print(f"Expected under {DIST}", file=sys.stderr)
        return 1
    for name in REQUIRED:
        path = DIST / f"{name}.html"
        print(f"ok {path.name} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
