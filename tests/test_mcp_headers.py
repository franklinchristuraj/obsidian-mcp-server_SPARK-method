"""SEP-2243 Mcp-Method / Mcp-Name header validation."""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("MCP_API_KEY", "test-key")

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402


class TestMcpHeaders(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(main.app)
        self.auth = {
            "Authorization": "Bearer test-key",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def test_modern_missing_mcp_method_rejected(self) -> None:
        response = self.client.post(
            "/mcp",
            headers={**self.auth, "Mcp-Protocol-Version": "2026-07-28"},
            json={"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}},
        )
        self.assertEqual(response.status_code, 400)
        err = response.json()["error"]
        self.assertEqual(err["code"], -32020)

    def test_modern_method_mismatch_rejected(self) -> None:
        response = self.client.post(
            "/mcp",
            headers={
                **self.auth,
                "Mcp-Protocol-Version": "2026-07-28",
                "Mcp-Method": "tools/list",
            },
            json={"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], -32020)

    def test_modern_name_mismatch_rejected(self) -> None:
        response = self.client.post(
            "/mcp",
            headers={
                **self.auth,
                "Mcp-Protocol-Version": "2026-07-28",
                "Mcp-Method": "tools/call",
                "Mcp-Name": "wrong",
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "ping", "arguments": {}},
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], -32020)

    def test_modern_matching_headers_succeed(self) -> None:
        response = self.client.post(
            "/mcp",
            headers={
                **self.auth,
                "Mcp-Protocol-Version": "2026-07-28",
                "Mcp-Method": "ping",
            },
            json={"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("pong", response.json()["result"]["message"].lower())

    def test_legacy_without_headers_succeeds(self) -> None:
        response = self.client.post(
            "/mcp",
            headers=self.auth,
            json={"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}},
        )
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
