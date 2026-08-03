"""resources/list enumerates folders only; notes remain readable via resources/read."""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from src.clients.obsidian_client import ObsidianClient
from src.resources.obsidian_resources import ObsidianResources


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
    return str(root)


class TestResourcesFoldersOnly(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.vault_path = _make_tmp_vault()
        os.environ["OBSIDIAN_VAULT_PATH"] = self.vault_path
        self.client = ObsidianClient()
        self.resources = ObsidianResources(self.client)

    def tearDown(self) -> None:
        shutil.rmtree(self.vault_path, ignore_errors=True)

    async def test_discover_lists_folders_not_notes(self) -> None:
        discovered = await self.resources.discover_resources()
        uris = [r.uri for r in discovered]
        mime_types = {r.mimeType for r in discovered}

        self.assertIn("obsidian://notes/", uris)
        self.assertTrue(any("personal" in u for u in uris))
        self.assertTrue(
            any("06_daily-notes" in u for u in uris),
            msg="daily-notes folder should remain browseable",
        )
        self.assertFalse(
            any(u.endswith(".md") for u in uris),
            msg="individual notes must not appear in resources/list",
        )
        self.assertEqual(mime_types, {"application/json"})

    async def test_read_note_via_uri_still_works(self) -> None:
        content = await self.resources.read_resource(
            "obsidian://notes/personal/06_daily-notes/2026-04-11.md"
        )
        self.assertEqual(content.mimeType, "text/markdown")
        self.assertIn("# Daily", content.text or "")

    def test_resource_template_covers_notes(self) -> None:
        templates = self.resources.list_resource_templates()
        self.assertEqual(len(templates), 1)
        self.assertEqual(templates[0].uriTemplate, "obsidian://notes/{+path}")


if __name__ == "__main__":
    unittest.main()
