"""Unit tests for create_note template rendering and empty-write guard."""
import unittest
from typing import Dict, Optional
from unittest.mock import AsyncMock

from src.clients.obsidian_client import ObsidianAPIError
from src.tools.obsidian_tools import ObsidianTools


class _MockObsidianClient:
    """Minimal async client for create_note template tests."""

    def __init__(self, templates: Optional[Dict[str, str]] = None):
        self.templates = dict(templates or {})
        self.created: list[tuple[str, str]] = []

    async def read_note(self, path: str) -> str:
        if path not in self.templates:
            raise ObsidianAPIError(f"Note not found: {path}", 404)
        return self.templates[path]

    async def create_note(
        self, path: str, content: str, create_folders: bool = True
    ) -> bool:
        self.created.append((path, content))
        return True


class TestCreateNoteTemplates(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tools = ObsidianTools()
        self.tools._vault_intel = None

    async def test_meeting_notes_alias_triggers_smart_builder(self) -> None:
        client = _MockObsidianClient()
        self.tools.client = client

        result = await self.tools.create_note(
            path="11_meeting-notes/2026-06-30-standup.md",
            content="",
            scope="work",
            use_template=True,
            template_vars={
                "title": "Daily Standup",
                "date": "2026-06-30",
                "discussion": "Reviewed sprint board.",
                "action_items": [{"task": "Follow up with design", "assignee": "Alex"}],
            },
        )

        self.assertTrue(client.created)
        _, written = client.created[0]
        self.assertGreater(len(written), 0)
        self.assertIn("Daily Standup", written)
        self.assertIn("Reviewed sprint board", written)
        self.assertEqual(result["metadata"]["template_source"], "smart-builder")
        self.assertTrue(result["metadata"]["path_normalized"])

    async def test_vault_template_title_date_substitution(self) -> None:
        template = "---\ndate: {{date}}\n---\n\n# {{title}}\n"
        client = _MockObsidianClient(
            {"work/00_system/templates/meeting-notes.md": template}
        )
        self.tools.client = client

        result = await self.tools.create_note(
            path="11_work-meeting-notes/2026-06-30-sync.md",
            content="",
            scope="work",
            use_template=True,
            template_vars={"title": "Partner Sync", "date": "2026-06-30"},
        )

        _, written = client.created[0]
        self.assertIn("# Partner Sync", written)
        self.assertIn("date: 2026-06-30", written)
        self.assertGreater(len(written), 0)
        self.assertEqual(result["metadata"]["template_source"], "vault")

    async def test_empty_vault_template_raises_without_write(self) -> None:
        client = _MockObsidianClient(
            {"work/00_system/templates/meeting-notes.md": ""}
        )
        self.tools.client = client

        with self.assertRaises(ValueError) as ctx:
            await self.tools.create_note(
                path="11_work-meeting-notes/empty-template.md",
                content="",
                scope="work",
                use_template=True,
                template_vars={"title": "Test", "date": "2026-06-30"},
            )

        self.assertIn("empty content", str(ctx.exception).lower())
        self.assertEqual(client.created, [])

    async def test_frontmatter_content_written_as_is(self) -> None:
        client = _MockObsidianClient()
        self.tools.client = client
        content = "---\ntitle: My Note\ndate: 2026-06-30\n---\n\nBody text."

        result = await self.tools.create_note(
            path="11_work-meeting-notes/custom.md",
            content=content,
            scope="work",
            use_template=True,
        )

        _, written = client.created[0]
        self.assertEqual(written, content)
        self.assertFalse(result["metadata"]["template_applied"])
        self.assertIn("frontmatter detected", result["content"][0]["text"])

    async def test_legacy_template_filename_fallback(self) -> None:
        legacy = "---\n---\n\n# {{title}} on {{date}}\n"
        client = _MockObsidianClient(
            {"work/00_system/templates/meeting-notes_template.md": legacy}
        )
        self.tools.client = client

        result = await self.tools.create_note(
            path="11_work-meeting-notes/legacy-fallback.md",
            content="",
            scope="work",
            use_template=True,
            template_vars={"title": "Legacy Meeting", "date": "2026-06-30"},
        )

        _, written = client.created[0]
        self.assertIn("# Legacy Meeting on 2026-06-30", written)
        self.assertEqual(result["metadata"]["template_source"], "vault")

    async def test_unknown_folder_with_empty_content_raises(self) -> None:
        client = _MockObsidianClient()
        self.tools.client = client

        with self.assertRaises(ValueError) as ctx:
            await self.tools.create_note(
                path="99_misc/unknown.md",
                content="",
                scope="work",
                use_template=True,
            )

        self.assertIn("empty content", str(ctx.exception).lower())
        self.assertEqual(client.created, [])


class TestReadVaultTemplate(unittest.IsolatedAsyncioTestCase):
    async def test_tries_fallback_when_primary_missing(self) -> None:
        from src.utils.template_utils import read_vault_template

        client = AsyncMock()
        client.read_note = AsyncMock(
            side_effect=[
                ObsidianAPIError("Note not found: work/00_system/templates/meeting-notes.md", 404),
                "# {{title}}\n",
            ]
        )

        content, path = await read_vault_template(
            client,
            [
                "work/00_system/templates/meeting-notes.md",
                "work/00_system/templates/meeting-notes_template.md",
            ],
        )

        self.assertEqual(content, "# {{title}}\n")
        self.assertEqual(path, "work/00_system/templates/meeting-notes_template.md")
        self.assertEqual(client.read_note.await_count, 2)


if __name__ == "__main__":
    unittest.main()
