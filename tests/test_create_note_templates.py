"""Unit tests for create_note template rendering and empty-write guard."""
import os
import tempfile
import unittest
from pathlib import Path
from typing import Dict, Optional
from unittest.mock import AsyncMock

from src.clients.obsidian_client import ObsidianAPIError
from src.tools.obsidian_tools import ObsidianTools


class _MockObsidianClient:
    """Minimal async client for create_note template tests."""

    def __init__(self, templates: Optional[Dict[str, str]] = None):
        self.templates = dict(templates or {})
        self.created: list[tuple[str, str]] = []
        self.vault_path = tempfile.mkdtemp(prefix="create-note-tpl-")

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
        self._vault = tempfile.mkdtemp(prefix="create-note-tpl-env-")
        for scope in ("personal", "passion", "work", "parallax"):
            Path(self._vault, scope).mkdir()
        os.environ["OBSIDIAN_VAULT_PATH"] = self._vault
        self.tools = ObsidianTools()
        self.tools._vault_intel = None

    async def asyncTearDown(self) -> None:
        import shutil

        shutil.rmtree(self._vault, ignore_errors=True)

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


class TestEngagementTemplateRouting(unittest.TestCase):
    def test_engagement_subtype_template_paths(self) -> None:
        from src.utils.template_utils import template_detector

        self.assertEqual(
            template_detector.get_template_path_for_folder(
                "12_engagements/x.md", "work", engagement_type="build-with-me"
            ),
            "work/00_system/templates/build-with-me-engagement.md",
        )
        self.assertEqual(
            template_detector.get_template_path_for_folder(
                "12_engagements/x.md", "work", engagement_type="technical-deep-dive"
            ),
            "work/00_system/templates/technical-deep-dive.md",
        )
        self.assertEqual(
            template_detector.get_template_path_for_folder(
                "12_engagements/x.md", "work", engagement_type="demo"
            ),
            "work/00_system/templates/ve-engagement.md",
        )
        self.assertEqual(
            template_detector.get_template_path_for_folder(
                "12_engagements/x.md", "work", engagement_type="delivery"
            ),
            "work/00_system/templates/delivery-engagement.md",
        )
        self.assertEqual(
            template_detector.get_template_path_for_folder(
                "12_engagements/x.md", "work", engagement_type="enablement"
            ),
            "work/00_system/templates/enablement-engagement.md",
        )

    def test_impact_engagement_types_in_vocabulary(self) -> None:
        from src.vault_intelligence.parser import ENGAGEMENT_TYPES

        self.assertIn("delivery", ENGAGEMENT_TYPES)
        self.assertIn("enablement", ENGAGEMENT_TYPES)

    def test_build_engagement_note_from_data_bwm_fields(self) -> None:
        from src.utils.template_utils import build_engagement_note_from_data

        fm, body = build_engagement_note_from_data(
            title="Claroty BWM",
            engagement_type="build-with-me",
            date="2026-07-01",
            customer="Claroty",
            trial_start="2026-07-01",
            trial_end="2026-07-31",
            next_touch="2026-07-08",
            next_touch_type="mid-trial-review",
        )
        self.assertEqual(fm["engagement_type"], "build-with-me")
        self.assertEqual(fm["trial_end"], "2026-07-31")
        self.assertIn("## Planned touchpoints", body)
        self.assertIn("## High-signal debrief", body)


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
