"""CIMD fetch, SSRF guards, and OAuth authorize integration."""
from __future__ import annotations

import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("MCP_API_KEY", "test-key")
os.environ["CIMD_CACHE_DB"] = os.path.join(
    os.path.dirname(__file__), "_tmp_cimd_cache.db"
)

from fastapi.testclient import TestClient  # noqa: E402

from src import cimd as cimd_mod  # noqa: E402
from src.cimd import CimdError, fetch_cimd, is_cimd_client_id, resolve_oauth_client  # noqa: E402
import main  # noqa: E402


class TestCimdHelpers(unittest.TestCase):
    def test_is_cimd_url(self) -> None:
        self.assertTrue(is_cimd_client_id("https://claude.ai/oauth/client.json"))
        self.assertFalse(is_cimd_client_id("opaque-client-id"))
        self.assertFalse(is_cimd_client_id("http://insecure.example/c.json"))


class TestCimdFetch(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_http(self) -> None:
        with self.assertRaises(CimdError):
            await fetch_cimd("http://example.com/client.json")

    async def test_ssrf_blocks_localhost(self) -> None:
        with self.assertRaises(CimdError):
            await fetch_cimd("https://localhost/client.json")

    async def test_happy_path_mocked(self) -> None:
        url = "https://example.com/oauth/client-metadata.json"
        doc = {
            "client_id": url,
            "client_name": "Example",
            "redirect_uris": ["https://example.com/callback"],
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"ok":true}'
        mock_resp.json.return_value = doc

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch.object(cimd_mod, "_is_public_hostname", return_value=True), patch(
            "src.cimd.httpx.AsyncClient", return_value=mock_client
        ), patch.object(cimd_mod, "_cache_get", return_value=None), patch.object(
            cimd_mod, "_cache_put"
        ):
            got = await fetch_cimd(url)
        self.assertEqual(got["client_name"], "Example")
        self.assertEqual(got["redirect_uris"], ["https://example.com/callback"])

    async def test_client_id_mismatch(self) -> None:
        url = "https://example.com/oauth/client-metadata.json"
        doc = {
            "client_id": "https://evil.example/other.json",
            "redirect_uris": ["https://example.com/callback"],
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"{}"
        mock_resp.json.return_value = doc
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch.object(cimd_mod, "_is_public_hostname", return_value=True), patch(
            "src.cimd.httpx.AsyncClient", return_value=mock_client
        ), patch.object(cimd_mod, "_cache_get", return_value=None):
            with self.assertRaises(CimdError) as ctx:
                await fetch_cimd(url)
        self.assertIn("does not match", str(ctx.exception))

    async def test_resolve_falls_back_to_dcr(self) -> None:
        async def get_dcr(cid: str):
            if cid == "dcr-abc":
                return {
                    "client_id": "dcr-abc",
                    "client_name": "DCR",
                    "redirect_uris": ["https://claude.ai/cb"],
                }
            return None

        resolved = await resolve_oauth_client(
            "dcr-abc", get_dcr_client=get_dcr
        )
        assert resolved is not None
        self.assertEqual(resolved["source"], "dcr")


class TestOAuthMetadata(unittest.TestCase):
    def test_metadata_advertises_cimd(self) -> None:
        client = TestClient(main.app)
        r = client.get("/.well-known/oauth-authorization-server")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body.get("client_id_metadata_document_supported"))
        self.assertIn("registration_endpoint", body)
        self.assertEqual(body.get("code_challenge_methods_supported"), ["S256"])


class TestAuthorizeCimd(unittest.TestCase):
    def test_authorize_with_cimd_client(self) -> None:
        url = "https://example.com/oauth/client-metadata.json"
        resolved = {
            "client_id": url,
            "client_name": "Example",
            "redirect_uris": ["https://example.com/callback"],
            "source": "cimd",
        }
        client = TestClient(main.app)
        with patch(
            "main.resolve_oauth_client", new=AsyncMock(return_value=resolved)
        ):
            r = client.get(
                "/authorize",
                params={
                    "response_type": "code",
                    "client_id": url,
                    "redirect_uri": "https://example.com/callback",
                    "code_challenge": "abc",
                    "code_challenge_method": "S256",
                    "state": "xyz",
                },
                follow_redirects=False,
            )
        self.assertEqual(r.status_code, 302)
        loc = r.headers["location"]
        self.assertIn("code=", loc)
        self.assertIn("iss=", loc)
        self.assertIn("state=xyz", loc)

    def test_dcr_register_still_works(self) -> None:
        client = TestClient(main.app)
        r = client.post(
            "/register",
            json={
                "client_name": "Test",
                "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
            },
        )
        self.assertEqual(r.status_code, 201)
        self.assertIn("client_id", r.json())


if __name__ == "__main__":
    unittest.main()
