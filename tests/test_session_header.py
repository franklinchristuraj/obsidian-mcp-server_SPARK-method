"""Transport-level tests for the Mcp-Session-Id response header.

HTTP header values must be latin-1 encodable, but workspace-key identities
are not: auth.py truncates them with a U+2026 ellipsis. Feeding one into the
fallback session id made uvicorn/starlette fail to encode the header, turning
every request from a client that doesn't echo Mcp-Session-Id (n8n, Make) into
a 500.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest

os.environ.setdefault("MCP_API_KEY", "test-key")

from fastapi.testclient import TestClient  # noqa: E402

from src import auth as auth_mod  # noqa: E402
from src import observability  # noqa: E402
import main  # noqa: E402

NON_ASCII_KEY = "sk_test_nonascii_identity"


class TestFallbackSessionId(unittest.TestCase):
    def test_fallback_session_id_is_latin1_encodable(self) -> None:
        session_id = observability.fallback_session_id("key:sk_personal_…")
        session_id.encode("latin-1")

    def test_fallback_session_id_is_visible_ascii(self) -> None:
        session_id = observability.fallback_session_id("key:sk_personal_…")
        self.assertTrue(all(0x21 <= ord(c) <= 0x7E for c in session_id))

    def test_fallback_session_id_is_stable_within_window(self) -> None:
        identity = "key:sk_personal_…"
        self.assertEqual(
            observability.fallback_session_id(identity),
            observability.fallback_session_id(identity),
        )

    def test_fallback_session_id_separates_identities(self) -> None:
        self.assertNotEqual(
            observability.fallback_session_id("key:sk_personal_…"),
            observability.fallback_session_id("key:sk_work_…"),
        )

    def test_fallback_session_id_does_not_embed_identity(self) -> None:
        """Hashed so truncated API-key prefixes never reach response headers
        or observability.db — matching the REDACT_ARGS posture."""
        identity = "key:sk_n8n_resea_…"
        session_id = observability.fallback_session_id(identity)
        self.assertNotIn("sk_n8n", session_id)
        self.assertNotIn(identity, session_id)
        self.assertRegex(session_id, r"^noid:[0-9a-f]{16}:\d+$")


class TestArgRedaction(unittest.TestCase):
    def test_dict_args_are_redacted_to_types(self) -> None:
        self.assertEqual(
            observability._redact({"query": "secret", "limit": 3}),
            {"query": "str", "limit": "int"},
        )

    def test_non_dict_args_do_not_raise(self) -> None:
        """A client can send `arguments` as a list; that must be recorded,
        not dropped, since malformed calls are worth observing."""
        for value in ([1, 2, 3], "a string", 7, None):
            with self.subTest(value=value):
                json.dumps(observability._redact(value))

    def test_non_dict_args_are_still_logged(self) -> None:
        observability._queue._queue.clear()
        observability.log_tool_call(
            session_id="s", client="unknown", tool_name="ping",
            args=[1, 2, 3], status="ok", error=None,
            latency_ms=0, response_bytes=0,
        )
        self.assertEqual(observability._queue.qsize(), 1)


class TestSessionClientCache(unittest.TestCase):
    def setUp(self) -> None:
        observability._session_clients.clear()

    def tearDown(self) -> None:
        observability._session_clients.clear()

    def test_cache_is_bounded(self) -> None:
        limit = observability._SESSION_CLIENTS_MAX
        for i in range(limit + 500):
            observability.register_session_client(f"sid-{i}", "Claude Desktop")
        self.assertLessEqual(len(observability._session_clients), limit)

    def test_eviction_is_least_recently_used(self) -> None:
        limit = observability._SESSION_CLIENTS_MAX
        observability.register_session_client("keep-me", "Claude Desktop")
        for i in range(limit - 1):
            observability.register_session_client(f"filler-{i}", "n8n")
        # Touching the old session must protect it from the next eviction wave.
        self.assertEqual(observability.resolve_client("keep-me"), "Desktop")
        for i in range(500):
            observability.register_session_client(f"late-{i}", "n8n")
        self.assertEqual(observability.resolve_client("keep-me"), "Desktop")

    def test_unknown_session_resolves_unknown(self) -> None:
        self.assertEqual(observability.resolve_client("never-seen"), "unknown")


class TestSessionHeaderOnRequest(unittest.TestCase):
    """End-to-end: a workspace key whose identity carries the ellipsis."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        )
        json.dump(
            {"keys": {NON_ASCII_KEY: {"scopes": ["personal"], "role": "user"}}},
            cls._tmp,
        )
        cls._tmp.close()
        cls._prev_path = os.environ.get("WORKSPACE_KEYS_PATH")
        os.environ["WORKSPACE_KEYS_PATH"] = cls._tmp.name
        auth_mod.clear_workspace_config_cache()

    @classmethod
    def tearDownClass(cls) -> None:
        if cls._prev_path is None:
            os.environ.pop("WORKSPACE_KEYS_PATH", None)
        else:
            os.environ["WORKSPACE_KEYS_PATH"] = cls._prev_path
        auth_mod.clear_workspace_config_cache()
        os.unlink(cls._tmp.name)

    def setUp(self) -> None:
        self.client = TestClient(main.app)
        self.headers = {
            "Authorization": f"Bearer {NON_ASCII_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def test_identity_under_test_actually_has_non_ascii(self) -> None:
        """Guard: if auth.py stops using the ellipsis, this suite stops
        testing anything and should be updated rather than silently pass."""
        with self.assertRaises(UnicodeEncodeError):
            f"key:{NON_ASCII_KEY[:12]}\u2026".encode("latin-1")

    def test_request_without_echoed_session_id_succeeds(self) -> None:
        response = self.client.post(
            "/mcp",
            headers=self.headers,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("tools", response.text)

    def test_response_carries_encodable_session_header(self) -> None:
        response = self.client.post(
            "/mcp",
            headers=self.headers,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        session_id = response.headers.get("mcp-session-id")
        self.assertIsNotNone(session_id)
        session_id.encode("latin-1")

    def test_notification_without_echoed_session_id_succeeds(self) -> None:
        response = self.client.post(
            "/mcp",
            headers=self.headers,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.content, b"")

    def test_echoed_session_id_is_preserved(self) -> None:
        response = self.client.post(
            "/mcp",
            headers={**self.headers, "Mcp-Session-Id": "client-supplied-id"},
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("mcp-session-id"), "client-supplied-id")


if __name__ == "__main__":
    unittest.main()
