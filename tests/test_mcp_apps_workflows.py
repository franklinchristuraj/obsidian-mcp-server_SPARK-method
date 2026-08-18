"""Tests for triage promote/archive and snapshot/debrief helpers."""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from src.apps.composers.prep_card import staleness_band
from src.apps.composers.snapshot_grid import compose_snapshot_grid
from src.apps.composers.triage import compose_triage_board
from src.apps.orchestrators.debrief import preview_debrief, submit_debrief
from src.apps.orchestrators.triage import archive_capture, promote_capture
from src.scope import WorkspaceContext, workspace_ctx
from src.tools.obsidian_tools import ObsidianTools


class TestTriagePromoteArchive(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.vault = Path(tempfile.mkdtemp(prefix="ziksaka-triage-"))
        for scope in ("personal", "passion", "work", "parallax"):
            (self.vault / scope).mkdir()
        seeds = self.vault / "01_seeds"
        seeds.mkdir()
        self.capture = seeds / "2026-07-31_test-capture.md"
        self.capture.write_text(
            "---\ntype: capture\nstatus: inbox\ncapture_type: post\n"
            'spark: "why this stopped my scroll"\ncaptured: 2026-07-31T09:12:00\n'
            "title: Agent eval\n---\n\nBody here.\n",
            encoding="utf-8",
        )
        self._old = os.environ.get("OBSIDIAN_VAULT_PATH")
        os.environ["OBSIDIAN_VAULT_PATH"] = str(self.vault)
        # Re-bind global tools client to temp vault
        from src.tools import obsidian_tools as ot_mod

        self.tools = ObsidianTools()
        ot_mod.obsidian_tools = self.tools
        # also update orchestrator import binding
        import src.apps.orchestrators.triage as triage_mod
        import src.apps.composers.triage as triage_comp

        triage_mod.obsidian_tools = self.tools
        triage_comp.obsidian_tools = self.tools
        self._ctx = workspace_ctx.set(
            WorkspaceContext(
                identity="test",
                allowed_scopes=("personal", "passion", "work", "parallax"),
                role="admin",
            )
        )

    def tearDown(self) -> None:
        workspace_ctx.reset(self._ctx)
        if self._old is None:
            os.environ.pop("OBSIDIAN_VAULT_PATH", None)
        else:
            os.environ["OBSIDIAN_VAULT_PATH"] = self._old
        shutil.rmtree(self.vault, ignore_errors=True)

    async def test_triage_board_lists_inbox(self) -> None:
        payload = await compose_triage_board(limit=50)
        self.assertEqual(payload["counts"]["total"], 1)
        self.assertEqual(payload["items"][0]["spark"], "why this stopped my scroll")
        self.assertIsNone(payload["items"][0]["suggested_scope"])

    async def test_promote_capture_to_work_seeds(self) -> None:
        result = await promote_capture(
            path="01_seeds/2026-07-31_test-capture.md",
            scope="work",
            target_folder="01_seeds",
            target_type="seed",
            title="Agent eval thread",
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["new_path"].startswith("work/01_seeds/"))
        self.assertFalse(self.capture.exists())
        dest = self.vault / result["new_path"]
        self.assertTrue(dest.is_file())
        text = dest.read_text(encoding="utf-8")
        self.assertIn("type: seed", text)

    async def test_archive_capture(self) -> None:
        # recreate capture if promote ran in another test order — fresh file
        if not self.capture.exists():
            self.capture.write_text(
                "---\ntype: capture\nstatus: inbox\n---\n\nx\n", encoding="utf-8"
            )
        result = await archive_capture("01_seeds/2026-07-31_test-capture.md")
        self.assertTrue(result["ok"])
        self.assertTrue(result["new_path"].startswith("99_archive/"))
        self.assertFalse(self.capture.exists())
        self.assertTrue((self.vault / result["new_path"]).is_file())


class TestSnapshotBlocked(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.vault = Path(tempfile.mkdtemp(prefix="ziksaka-snap-"))
        (self.vault / "work" / "12_engagements").mkdir(parents=True)
        note = self.vault / "work" / "12_engagements" / "2026-07-14_4flow-bwm.md"
        note.write_text(
            "---\ntype: engagement\nengagement_type: build-with-me\n"
            "date: 2026-07-14\ncustomer: 4flow\n---\n\n# 4flow\n",
            encoding="utf-8",
        )
        self._old = os.environ.get("OBSIDIAN_VAULT_PATH")
        os.environ["OBSIDIAN_VAULT_PATH"] = str(self.vault)
        from src.tools import obsidian_tools as ot_mod
        import src.apps.composers.snapshot_grid as sg

        self.tools = ObsidianTools()
        ot_mod.obsidian_tools = self.tools
        sg.obsidian_tools = self.tools
        self._ctx = workspace_ctx.set(
            WorkspaceContext(
                identity="test",
                allowed_scopes=("work",),
                role="admin",
            )
        )

    def tearDown(self) -> None:
        workspace_ctx.reset(self._ctx)
        if self._old is None:
            os.environ.pop("OBSIDIAN_VAULT_PATH", None)
        else:
            os.environ["OBSIDIAN_VAULT_PATH"] = self._old
        shutil.rmtree(self.vault, ignore_errors=True)

    async def test_missing_org_id_goes_to_blocked(self) -> None:
        payload = await compose_snapshot_grid(scope="work")
        self.assertTrue(any(b["reason"] == "no org_id" for b in payload["blocked"]))
        self.assertEqual(payload["orgs"], [])


class TestDebriefIdempotency(unittest.IsolatedAsyncioTestCase):
    async def test_preview_lists_writes(self) -> None:
        plan = await preview_debrief(
            {
                "date": "2026-08-03",
                "customer": {"query": "Claroty"},
                "entity_gaps": [
                    {
                        "name": "Claroty",
                        "entity_type": "customer",
                        "exists": False,
                        "will_create": True,
                    }
                ],
                "create_event": True,
            },
            scope="work",
        )
        self.assertGreaterEqual(plan["write_count"], 3)
        ops = {w["op"] for w in plan["writes"]}
        self.assertIn("create_event", ops)

    async def test_duplicate_submit_is_noop(self) -> None:
        # Without a vault, create_note will fail — still verify idempotency cache
        # after a successful cached write by planting cache.
        from src.apps.orchestrators import debrief as dmod

        key = "test-idem-key-xyz"
        planted = {
            "written": [{"op": "create_note", "path": "x.md", "ok": True}],
            "failed": [],
            "idempotency_key": key,
        }
        dmod._idem_put(key, planted)
        result = await submit_debrief({"date": "2026-08-03"}, key, scope="work")
        self.assertTrue(result.get("idempotent_replay"))
        self.assertEqual(result["written"], planted["written"])


class TestStaleness(unittest.TestCase):
    def test_bands(self) -> None:
        self.assertEqual(staleness_band(75), "stale")


if __name__ == "__main__":
    unittest.main()
