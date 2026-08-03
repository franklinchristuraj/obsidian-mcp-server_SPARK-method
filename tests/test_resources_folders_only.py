"""resources/list = workspace roots + pins; notes via read/templates; scope-filtered."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from src.clients.obsidian_client import ObsidianClient
from src.resources.obsidian_resources import CURATED_ROOT_PINS, ObsidianResources
from src.scope import WorkspaceContext, workspace_ctx


def _make_tmp_vault() -> str:
    root = Path(tempfile.mkdtemp(prefix="obsidian-resources-test-"))
    for scope in ("personal", "passion", "work"):
        (root / scope).mkdir()
    daily = root / "personal" / "06_daily-notes"
    daily.mkdir(parents=True)
    (daily / "2026-04-11.md").write_text("# Daily\n", encoding="utf-8")
    entities = root / "work" / "entities" / "customer"
    entities.mkdir(parents=True)
    (entities / "acme.md").write_text(
        "---\nentity_type: customer\n---\n# Acme\n", encoding="utf-8"
    )
    (root / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    (root / "index.md").write_text("# Index\n", encoding="utf-8")
    (root / "CLAUDE.md").write_text("# Claude\n", encoding="utf-8")
    # Deep folder that must NOT appear in resources/list
    deep = root / "work" / "11_meeting-notes"
    deep.mkdir(parents=True)
    (deep / "2026-01-01.md").write_text("# Meeting\n", encoding="utf-8")
    return str(root)


class TestResourcesWorkspaceRoots(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.vault_path = _make_tmp_vault()
        os.environ["OBSIDIAN_VAULT_PATH"] = self.vault_path
        self.client = ObsidianClient()
        self.resources = ObsidianResources(self.client)
        self._ctx_token = workspace_ctx.set(
            WorkspaceContext(
                identity="test-all",
                allowed_scopes=("personal", "passion", "work"),
                role="admin",
            )
        )

    def tearDown(self) -> None:
        workspace_ctx.reset(self._ctx_token)
        shutil.rmtree(self.vault_path, ignore_errors=True)

    async def test_discover_lists_workspace_roots_and_pins_only(self) -> None:
        discovered = await self.resources.discover_resources()
        uris = [r.uri for r in discovered]

        self.assertIn("obsidian://notes/", uris)
        for scope in ("personal", "passion", "work"):
            self.assertIn(f"obsidian://notes/{scope}/", uris)
        for pin in CURATED_ROOT_PINS:
            self.assertIn(f"obsidian://notes/{pin}", uris)

        self.assertFalse(
            any("06_daily-notes" in u for u in uris),
            msg="deep folders must not appear in resources/list",
        )
        self.assertFalse(
            any("11_meeting-notes" in u for u in uris),
            msg="meeting-notes folder must not be listed",
        )
        self.assertFalse(
            any(u.endswith("acme.md") for u in uris),
            msg="entity notes must not appear in resources/list",
        )
        ui_count = sum(1 for u in uris if u.startswith("ui://"))
        self.assertEqual(len(discovered), 1 + 3 + 3 + ui_count)  # root + workspaces + pins + UI
        self.assertGreaterEqual(ui_count, 1)

    async def test_discover_respects_work_only_scope(self) -> None:
        token = workspace_ctx.set(
            WorkspaceContext(
                identity="work-only",
                allowed_scopes=("work",),
                role="viewer",
            )
        )
        try:
            discovered = await self.resources.discover_resources()
            uris = [r.uri for r in discovered]
            self.assertIn("obsidian://notes/work/", uris)
            self.assertNotIn("obsidian://notes/personal/", uris)
            self.assertNotIn("obsidian://notes/passion/", uris)
            # Root pins remain available
            self.assertIn("obsidian://notes/AGENTS.md", uris)
        finally:
            workspace_ctx.reset(token)

    async def test_read_denies_disallowed_workspace(self) -> None:
        token = workspace_ctx.set(
            WorkspaceContext(
                identity="work-only",
                allowed_scopes=("work",),
                role="viewer",
            )
        )
        try:
            with self.assertRaises(PermissionError):
                await self.resources.read_resource(
                    "obsidian://notes/personal/06_daily-notes/2026-04-11.md"
                )
        finally:
            workspace_ctx.reset(token)

    async def test_read_note_via_uri_still_works(self) -> None:
        content = await self.resources.read_resource(
            "obsidian://notes/personal/06_daily-notes/2026-04-11.md"
        )
        self.assertEqual(content.mimeType, "text/markdown")
        self.assertIn("# Daily", content.text or "")

    async def test_read_root_pin(self) -> None:
        content = await self.resources.read_resource("obsidian://notes/AGENTS.md")
        self.assertEqual(content.mimeType, "text/markdown")
        self.assertIn("# Agents", content.text or "")

    async def test_read_workspace_folder_lists_children(self) -> None:
        content = await self.resources.read_resource("obsidian://notes/work/")
        self.assertEqual(content.mimeType, "application/json")
        data = json.loads(content.text or "{}")
        folder_names = {f["name"] for f in data.get("folders", [])}
        self.assertIn("entities", folder_names)

    def test_resource_templates(self) -> None:
        templates = self.resources.list_resource_templates()
        uris = {t.uriTemplate for t in templates}
        self.assertIn("obsidian://notes/{+path}", uris)
        self.assertIn("obsidian://notes/{scope}/06_daily-notes/{date}.md", uris)
        self.assertIn("obsidian://notes/work/entities/{type}/{slug}.md", uris)

    def test_ui_registry_lists_bundles(self) -> None:
        from src.apps.paths import split_ui_uri

        resources = self.resources.list_ui_resources()
        apps = {split_ui_uri(r.uri)[0] for r in resources}
        self.assertIn("smoke", apps)
        self.assertEqual(
            self.resources.build_ui_uri("impact/rollup"),
            "ui://ziksaka/impact/rollup",
        )


if __name__ == "__main__":
    unittest.main()
