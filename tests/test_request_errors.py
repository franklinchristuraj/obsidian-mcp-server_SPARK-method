"""Request-level failures must ride on HTTP 200, not a transport-killing 404.

In Streamable HTTP a non-2xx on the MCP endpoint reads as "session gone", so a
client tears the connection down instead of surfacing the JSON-RPC error. That
turned a missing note into "Connection closed" on the caller's side. Only an
unknown *method* keeps the 404 / -32601 path.
"""
from __future__ import annotations

import os
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("MCP_API_KEY", "test-key")

from fastapi.testclient import TestClient  # noqa: E402

from src.auth import verify_api_key  # noqa: E402
from src.clients.obsidian_client import ObsidianAPIError  # noqa: E402
from src.mcp_server import (  # noqa: E402
    INTERNAL_ERROR,
    INVALID_PARAMS,
    RESOURCE_NOT_FOUND,
    InvalidParamsError,
    MCPRequestError,
    ResourceNotFoundError,
    mcp_handler,
)
from src.scope import WorkspaceContext  # noqa: E402
import main  # noqa: E402


_CTX = WorkspaceContext(
    identity="key:test",
    allowed_scopes=("personal", "passion", "work", "parallax"),
    role="user",
)


class TestErrorTransport(unittest.TestCase):
    """main.py's mapping from handler exception -> HTTP status + JSON-RPC code."""

    def setUp(self) -> None:
        main.app.dependency_overrides[verify_api_key] = lambda: _CTX
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        main.app.dependency_overrides.pop(verify_api_key, None)

    def _post(self, method: str, params: dict) -> object:
        return self.client.post(
            "/mcp",
            headers={"Content-Type": "application/json"},
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        )

    def test_missing_resource_is_200_with_resource_not_found(self) -> None:
        with patch.object(
            mcp_handler,
            "handle_request",
            AsyncMock(
                side_effect=ResourceNotFoundError(
                    "Resource not found: obsidian://notes/passion/index.md"
                )
            ),
        ):
            response = self._post(
                "resources/read", {"uri": "obsidian://notes/passion/index.md"}
            )

        self.assertEqual(response.status_code, 200)
        error = response.json()["error"]
        self.assertEqual(error["code"], RESOURCE_NOT_FOUND)
        self.assertIn("passion/index.md", error["message"])

    def test_invalid_params_is_200(self) -> None:
        with patch.object(
            mcp_handler,
            "handle_request",
            AsyncMock(side_effect=InvalidParamsError("Invalid cursor: 'nope'")),
        ):
            response = self._post("tools/list", {"cursor": "nope"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["error"]["code"], INVALID_PARAMS)

    def test_internal_failure_is_200(self) -> None:
        with patch.object(
            mcp_handler,
            "handle_request",
            AsyncMock(side_effect=MCPRequestError(INTERNAL_ERROR, "disk on fire")),
        ):
            response = self._post("resources/read", {"uri": "obsidian://notes/x.md"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["error"]["code"], INTERNAL_ERROR)

    def test_unknown_method_still_404(self) -> None:
        response = self._post("does/not/exist", {})

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], -32601)


class TestResourceReadMapping(unittest.IsolatedAsyncioTestCase):
    """_handle_resources_read turns vault failures into typed request errors."""

    async def _read(self, side_effect) -> None:
        handler = type("H", (), {"read_resource": AsyncMock(side_effect=side_effect)})()
        with patch(
            "src.resources.obsidian_resources.get_obsidian_resources",
            return_value=handler,
        ):
            await mcp_handler._handle_resources_read(
                {"uri": "obsidian://notes/passion/index.md"}
            )

    async def test_note_not_found(self) -> None:
        with self.assertRaises(ResourceNotFoundError) as caught:
            await self._read(ObsidianAPIError("Note not found: passion/index.md", 404))
        self.assertEqual(caught.exception.code, RESOURCE_NOT_FOUND)

    async def test_out_of_scope_path(self) -> None:
        with self.assertRaises(ResourceNotFoundError) as caught:
            await self._read(PermissionError("Access denied to workspace `work`"))
        self.assertIn("Access denied", caught.exception.message)

    async def test_bad_uri_scheme(self) -> None:
        with self.assertRaises(InvalidParamsError) as caught:
            await self._read(ValueError("Invalid URI scheme"))
        self.assertEqual(caught.exception.code, INVALID_PARAMS)

    async def test_vault_failure_is_internal(self) -> None:
        with self.assertRaises(MCPRequestError) as caught:
            await self._read(ObsidianAPIError("Filesystem exploded", 500))
        self.assertEqual(caught.exception.code, INTERNAL_ERROR)

    async def test_missing_uri(self) -> None:
        with self.assertRaises(InvalidParamsError):
            await mcp_handler._handle_resources_read({})


if __name__ == "__main__":
    unittest.main()
