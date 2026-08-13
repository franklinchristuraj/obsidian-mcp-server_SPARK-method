#!/usr/bin/env python3
"""
Mock Filesystem Vault for Testing

Creates a disposable tmp-filesystem vault (personal/passion/work/parallax scope
folders + a few sample notes) and prints its path so you can point
OBSIDIAN_VAULT_PATH at it. Replaces the old mock Obsidian REST API server -
there's no REST API to mock anymore, just a directory tree.
"""
import sys
import tempfile
from pathlib import Path

MOCK_NOTES = {
    "personal/06_daily-notes/2024-01-01.md": (
        "---\ntype: daily-note\n---\n\n# 2024-01-01\n\nMock daily note.\n"
    ),
    "work/02_projects/test-project.md": (
        "---\ntype: project\nstatus: active\n---\n\n"
        "# Test Project\n\nMock project note.\n\n"
        "## Links\n[[work/02_projects/test-project]]\n\n#testing #mock\n"
    ),
    "passion/01_seeds/random-thoughts.md": (
        "---\ntype: seed\n---\n\n# Random Thoughts\n\nMock seed note.\n"
    ),
}


def create_mock_vault() -> str:
    root = Path(tempfile.mkdtemp(prefix="obsidian-mock-vault-"))
    for scope in ("personal", "passion", "work", "parallax"):
        (root / scope).mkdir()
    for rel_path, content in MOCK_NOTES.items():
        full = root / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
    return str(root)


if __name__ == "__main__":
    vault_path = create_mock_vault()
    print("🚀 Created mock filesystem vault")
    print(f"📍 Path: {vault_path}")
    print(f"📝 Sample notes: {len(MOCK_NOTES)}")
    print("\n💡 Point the server at it:")
    print(f"   export OBSIDIAN_VAULT_PATH={vault_path}")
    print("\n🛑 Remember to delete it when done:")
    print(f"   rm -rf {vault_path}")
    sys.exit(0)
