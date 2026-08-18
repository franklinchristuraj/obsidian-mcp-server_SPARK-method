"""Multi-worker shared SQLite task store tests."""
from __future__ import annotations

import os
import tempfile
import unittest

from src.tasks import (
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_QUEUED,
    STATUS_WORKING,
    TaskStore,
)


class TestMultiWorkerTaskStore(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self.path = self._tmp.name
        self.a = TaskStore(db_path=self.path)
        self.b = TaskStore(db_path=self.path)
        await self.a.init_db()

    def tearDown(self) -> None:
        os.unlink(self.path)

    async def test_enqueue_claim_across_instances(self) -> None:
        task_id = await self.a.enqueue_task(
            identity="key:a",
            tool_name="lint_vault",
            arguments={"scope": "work", "fix": False},
            auth={"identity": "key:a", "allowed_scopes": ["work"], "role": "user"},
        )
        claimed = await self.b.claim_next(worker_id="worker-b")
        assert claimed is not None
        self.assertEqual(claimed["task_id"], task_id)
        self.assertEqual(claimed["tool_name"], "lint_vault")
        self.assertEqual(claimed["arguments"]["scope"], "work")

        await self.b.complete_task(task_id, result={"ok": True})
        got = await self.a.get_task(task_id, "key:a")
        assert got is not None
        self.assertEqual(got["status"], STATUS_COMPLETED)
        self.assertEqual(got["result"], {"ok": True})

    async def test_cancel_queued_visible_to_other_instance(self) -> None:
        task_id = await self.a.enqueue_task(
            identity="key:a",
            tool_name="build_context",
            arguments={},
            auth={"identity": "key:a", "allowed_scopes": ["work"], "role": "user"},
        )
        ok = await self.b.cancel_task(task_id, "key:a")
        self.assertTrue(ok)
        got = await self.a.get_task(task_id, "key:a")
        assert got is not None
        self.assertEqual(got["status"], STATUS_CANCELLED)
        # Claim should not pick cancelled
        claimed = await self.a.claim_next(worker_id="worker-a")
        self.assertIsNone(claimed)

    async def test_complete_skips_if_cancelled(self) -> None:
        task_id = await self.a.enqueue_task(
            identity="key:a",
            tool_name="get_dossier",
            arguments={},
            auth={"identity": "key:a", "allowed_scopes": ["work"], "role": "user"},
        )
        claimed = await self.a.claim_next(worker_id="w1")
        assert claimed is not None
        await self.b.cancel_task(task_id, "key:a")
        finished = await self.a.complete_task(task_id, result={"late": True})
        self.assertFalse(finished)
        got = await self.a.get_task(task_id, "key:a")
        assert got is not None
        self.assertEqual(got["status"], STATUS_CANCELLED)

    async def test_identity_isolation(self) -> None:
        task_id = await self.a.enqueue_task(
            identity="key:a",
            tool_name="lint_vault",
            arguments={},
            auth={"identity": "key:a", "allowed_scopes": [], "role": "user"},
        )
        self.assertIsNone(await self.b.get_task(task_id, "key:b"))


if __name__ == "__main__":
    unittest.main()
