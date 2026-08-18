"""Tasks extension: async heavy tools + tasks/get polling."""
from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("MCP_API_KEY", "test-key")

from fastapi.testclient import TestClient  # noqa: E402

from src import request_context  # noqa: E402
from src.request_context import RequestMeta  # noqa: E402
from src.scope import WorkspaceContext, workspace_ctx  # noqa: E402
from src.tasks import TaskStore, task_handle_result  # noqa: E402
import main  # noqa: E402


class TestTaskStore(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self.store = TaskStore(db_path=self._tmp.name)
        await self.store.init_db()

    def tearDown(self) -> None:
        os.unlink(self._tmp.name)

    async def test_create_complete_get(self) -> None:
        task_id = await self.store.create_task(identity="key:a", tool_name="lint_vault")
        got = await self.store.get_task(task_id, "key:a")
        assert got is not None
        self.assertEqual(got["status"], "working")
        await self.store.complete_task(task_id, result={"ok": True})
        got = await self.store.get_task(task_id, "key:a")
        assert got is not None
        self.assertEqual(got["status"], "completed")
        self.assertEqual(got["result"], {"ok": True})

    async def test_identity_isolation(self) -> None:
        task_id = await self.store.create_task(identity="key:a", tool_name="lint_vault")
        self.assertIsNone(await self.store.get_task(task_id, "key:b"))


class TestTaskHandleResult(unittest.TestCase):
    def test_handle_shape(self) -> None:
        result = task_handle_result("tid-1", "lint_vault")
        self.assertIn("taskId", result["structuredContent"])
        self.assertEqual(result["structuredContent"]["status"], "working")


class TestTasksHttp(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(main.app)
        self.headers = {
            "Authorization": "Bearer test-key",
            "Content-Type": "application/json",
        }

    def test_tasks_get_unknown(self) -> None:
        response = self.client.post(
            "/mcp",
            headers=self.headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tasks/get",
                "params": {"taskId": "does-not-exist"},
            },
        )
        # METHOD_NOT_FOUND path for ValueError from handler
        self.assertIn(response.status_code, (404, 500, 200))
        body = response.json()
        if "error" in body:
            self.assertIn("Unknown taskId", str(body["error"]))

    def test_async_tool_returns_handle_when_client_supports_tasks(self) -> None:
        meta = RequestMeta(
            protocol_version="2026-07-28",
            client_capabilities={
                "extensions": {"io.modelcontextprotocol/tasks": {}}
            },
            is_modern=True,
        )
        auth = WorkspaceContext(
            identity="key:test",
            allowed_scopes=("personal",),
            role="user",
            display_name="test",
            write_scopes=("personal",),
        )

        async def _run() -> dict:
            token_m = request_context.request_meta.set(meta)
            token_w = workspace_ctx.set(auth)
            try:
                with patch.object(
                    main.mcp_handler,
                    "_run_obsidian_tool",
                    new=AsyncMock(
                        return_value={"content": [{"type": "text", "text": "done"}]}
                    ),
                ):
                    result = await main.mcp_handler._maybe_run_as_task(
                        "lint_vault", {"scope": "work", "fix": False}
                    )
                return result  # type: ignore[return-value]
            finally:
                request_context.request_meta.reset(token_m)
                workspace_ctx.reset(token_w)

        result = asyncio.run(_run())
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("taskId", result["structuredContent"])
        self.assertEqual(result["structuredContent"]["toolName"], "lint_vault")

    def test_sync_when_client_lacks_tasks(self) -> None:
        meta = RequestMeta(protocol_version="2025-06-18", is_modern=False)

        async def _run() -> object:
            token_m = request_context.request_meta.set(meta)
            try:
                return await main.mcp_handler._maybe_run_as_task(
                    "lint_vault", {"scope": "work"}
                )
            finally:
                request_context.request_meta.reset(token_m)

        result = asyncio.run(_run())
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
