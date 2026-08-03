"""Transport-level tests for JSON-RPC notification responses.

A notification response carries no body. Returning a body alongside an
empty-body status code makes uvicorn abort the ASGI response
("Response content longer than Content-Length"), which breaks the client
mid-session — Claude stops fetching MCP App UI resources.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("MCP_API_KEY", "test-key")

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402


class TestNotificationResponse(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(main.app)
        self.headers = {
            "Authorization": f"Bearer {os.environ['MCP_API_KEY']}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

    def _notify(self, method: str = "notifications/initialized"):
        return self.client.post(
            "/mcp",
            headers=self.headers,
            json={"jsonrpc": "2.0", "method": method},
        )

    def test_notification_returns_empty_accepted_body(self) -> None:
        response = self._notify()
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.content, b"")

    def test_notification_content_length_matches_body(self) -> None:
        """The regression itself: declared length must match the bytes sent."""
        response = self._notify()
        declared = response.headers.get("content-length")
        if declared is not None:
            self.assertEqual(int(declared), len(response.content))
        self.assertNotIn(b"null", response.content)

    def test_request_after_notification_still_works(self) -> None:
        """A broken notification response must not poison the session."""
        self._notify()
        response = self.client.post(
            "/mcp",
            headers=self.headers,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("tools", response.text)


if __name__ == "__main__":
    unittest.main()
