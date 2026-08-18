"""Tests for server/discover and 2026-07-28 dual-compat discovery."""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("MCP_API_KEY", "test-key")

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402


class TestServerDiscover(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(main.app)
        self.headers = {
            "Authorization": "Bearer test-key",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Mcp-Protocol-Version": "2026-07-28",
            "Mcp-Method": "server/discover",
        }

    def test_discover_returns_capabilities_without_session(self) -> None:
        response = self.client.post(
            "/mcp",
            headers=self.headers,
            json={"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {}},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("result", body)
        result = body["result"]
        self.assertEqual(result["protocolVersion"], "2026-07-28")
        self.assertIn("capabilities", result)
        self.assertIn("io.modelcontextprotocol/tasks", result["capabilities"].get("extensions", {}))
        self.assertIn("io.modelcontextprotocol/ui", result["capabilities"].get("extensions", {}))
        self.assertIn("serverInfo", result)

    def test_legacy_initialize_still_works(self) -> None:
        response = self.client.post(
            "/mcp",
            headers={
                "Authorization": "Bearer test-key",
                "Content-Type": "application/json",
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"]["protocolVersion"], "2025-06-18")


if __name__ == "__main__":
    unittest.main()
