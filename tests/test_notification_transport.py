"""Transport-level tests for JSON-RPC notification responses.

A notification response carries no body. Returning a body alongside an
empty-body status code makes uvicorn abort the ASGI response
("Response content longer than Content-Length"), which breaks the client
mid-session — Claude stops fetching MCP App UI resources.
"""
from __future__ import annotations

import json
import os
import unittest
from unittest import mock

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


class TestSessionHeaderEncoding(unittest.TestCase):
    """The fallback session id embeds the caller identity, which may be Unicode.

    Header values are latin-1 only, so an un-coerced identity raised while the
    response was being built — surfacing as a 500 with a null id, and in
    production as uvicorn's "Response content longer than Content-Length".
    """

    def setUp(self) -> None:
        self.client = TestClient(main.app)
        self.headers = {
            "Authorization": f"Bearer {os.environ['MCP_API_KEY']}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

    def test_header_safe_coerces_non_latin1(self) -> None:
        self.assertEqual(main._header_safe("plain-ascii"), "plain-ascii")
        coerced = main._header_safe("noid:key:abcdef\u2026:42")
        coerced.encode("latin-1")
        self.assertNotIn("\u2026", coerced)

    def test_unicode_fallback_identity_returns_empty_202(self) -> None:
        """No Mcp-Session-Id header, so the Unicode-bearing fallback is used."""
        with mock.patch.object(
            main.observability,
            "fallback_session_id",
            return_value="noid:key:abcdef\u2026:42",
        ):
            response = self.client.post(
                "/mcp",
                headers=self.headers,
                json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            )
        self.assertEqual(response.status_code, 202, msg=response.text)
        self.assertEqual(response.content, b"")

    def test_api_key_identity_is_header_encodable(self) -> None:
        from src.observability import fallback_session_id

        fallback_session_id("key:sk_admin_abc...").encode("latin-1")


def _sse_data_lines(text: str) -> list[str]:
    return [line[len("data: "):] for line in text.splitlines() if line.startswith("data: ")]


class TestSseStreamIsJsonRpcOnly(unittest.IsolatedAsyncioTestCase):
    """Every SSE data event must be a JSON-RPC message.

    The prior stream appended OpenAI-style content chunks and a `data: [DONE]`
    sentinel; `[DONE]` is not valid JSON, so MCP clients aborted the stream with
    "Unexpected token 'D', "[DONE]" is not valid JSON", dropping the session.
    """

    async def test_generator_emits_single_jsonrpc_event(self) -> None:
        response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"tools": [{"name": f"t{i}"} for i in range(40)]},
        }
        text = "".join(
            [
                chunk
                async for chunk in main.create_sse_stream(
                    response, result_data=list(range(40)), enable_streaming=True
                )
            ]
        )
        self.assertNotIn("[DONE]", text)
        data_lines = _sse_data_lines(text)
        self.assertEqual(len(data_lines), 1, msg=text)
        msg = json.loads(data_lines[0])
        self.assertEqual(msg["jsonrpc"], "2.0")
        self.assertIn("tools", msg["result"])


class TestSseStreamEndToEnd(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(main.app)
        self.headers = {
            "Authorization": f"Bearer {os.environ['MCP_API_KEY']}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }

    def test_streamed_tools_list_is_all_valid_json(self) -> None:
        response = self.client.post(
            "/mcp",
            headers=self.headers,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        self.assertEqual(response.status_code, 200)
        body = response.text
        self.assertNotIn("[DONE]", body)
        if "text/event-stream" in response.headers.get("content-type", ""):
            for data in _sse_data_lines(body):
                if not data.strip():
                    continue
                parsed = json.loads(data)  # would raise on a [DONE] sentinel
                self.assertEqual(parsed.get("jsonrpc"), "2.0")


if __name__ == "__main__":
    unittest.main()
