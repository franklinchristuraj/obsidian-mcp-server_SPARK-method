"""SEP-2549 cache hints on list/read results."""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("MCP_API_KEY", "test-key")

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402


class TestCacheHints(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(main.app)
        self.headers = {
            "Authorization": "Bearer test-key",
            "Content-Type": "application/json",
        }

    def test_tools_list_has_cache_hints(self) -> None:
        response = self.client.post(
            "/mcp",
            headers=self.headers,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()["result"]
        self.assertEqual(result["ttlMs"], 300_000)
        self.assertEqual(result["cacheScope"], "private")
        self.assertIn("tools", result)

    def test_prompts_list_has_cache_hints(self) -> None:
        response = self.client.post(
            "/mcp",
            headers=self.headers,
            json={"jsonrpc": "2.0", "id": 1, "method": "prompts/list", "params": {}},
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()["result"]
        self.assertEqual(result["ttlMs"], 300_000)
        self.assertEqual(result["cacheScope"], "private")


if __name__ == "__main__":
    unittest.main()
