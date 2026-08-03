#!/usr/bin/env python3
"""Sync the shared shell bridge into the single-file MCP App bundles.

The committed apps/dist/*.html bundles are what the server serves, but the
bridge inside them is generated from apps/packages/shell/bridge.js. Run with
--check in CI to fail when a bundle has drifted from the shared source.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "apps" / "dist"
BRIDGE_SRC = ROOT / "apps" / "packages" / "shell" / "bridge.js"
START = "<!-- shell:bridge:start -->"
END = "<!-- shell:bridge:end -->"
BLOCK_RE = re.compile(
    re.escape(START) + r".*?" + re.escape(END),
    re.S,
)
REQUIRED = (
    "smoke",
    "prep-card",
    "lint-queue",
    "snapshot-entry",
    "debrief-form",
    "triage-board",
)


def expected_block() -> str:
    return f"{START}\n<script>\n{BRIDGE_SRC.read_text()}</script>\n{END}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify bundles are in sync instead of rewriting them",
    )
    args = parser.parse_args()

    missing = [name for name in REQUIRED if not (DIST / f"{name}.html").is_file()]
    if missing:
        print(f"Missing UI bundles: {missing}", file=sys.stderr)
        print(f"Expected under {DIST}", file=sys.stderr)
        return 1

    block = expected_block()
    stale: list[str] = []
    for name in REQUIRED:
        path = DIST / f"{name}.html"
        text = path.read_text()
        if START not in text or END not in text:
            print(f"{path.name}: missing bridge markers", file=sys.stderr)
            return 1
        updated = BLOCK_RE.sub(lambda _: block, text, count=1)
        if updated == text:
            print(f"ok {path.name} ({path.stat().st_size} bytes)")
            continue
        if args.check:
            stale.append(path.name)
            continue
        path.write_text(updated)
        print(f"updated {path.name} ({path.stat().st_size} bytes)")

    if stale:
        print(
            f"Bundles out of sync with {BRIDGE_SRC.name}: {stale}\n"
            "Run: python scripts/build_apps.py",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
