"""M2 security fixes: header-only keys, hashed tokens, /revoke, strict /authorize, scoped keys.

Every test uses its own temporary token DB (never the tokens.db in the working
directory), so running the suite inside a deployed checkout cannot touch prod state.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("MCP_API_KEY", "test-key")

from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from src import auth as auth_mod  # noqa: E402
from src.scope import (  # noqa: E402
    active_scopes_for_read,
    resolve_scoped_path,
    resolve_write_scope,
)
from src.token_store import TokenStore  # noqa: E402


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class _TempStoreMixin:
    """A fresh, initialised TokenStore in a temp dir, swapped in for main.token_store."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmpdir.name, "tokens.db")
        self.store = TokenStore(db_path=self.db_path)
        asyncio.run(self.store.init_db())
        self._patch = patch.object(main, "token_store", self.store)
        self._patch.start()

    def tearDown(self) -> None:
        self._patch.stop()
        self._tmpdir.cleanup()

    def _rows(self, sql: str) -> list:
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute(sql).fetchall()
        finally:
            conn.close()


def _request(headers: dict, query: dict | None = None) -> MagicMock:
    req = MagicMock()
    req.headers = headers
    req.query_params = query or {}
    return req


class TestHeaderOnlyKeys(unittest.TestCase):
    """Keys in query strings leak into proxy logs; only headers are accepted."""

    def setUp(self) -> None:
        self._env = patch.dict(
            os.environ,
            {"MCP_API_KEY": "secret-key", "MCP_REQUIRE_AUTH": "true",
             "WORKSPACE_KEYS_PATH": "/nonexistent/workspace_keys.json"},
        )
        self._env.start()
        auth_mod.clear_workspace_config_cache()

    def tearDown(self) -> None:
        self._env.stop()
        auth_mod.clear_workspace_config_cache()

    def test_query_param_key_is_rejected(self) -> None:
        req = _request({}, {"api_key": "secret-key"})
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(auth_mod.verify_api_key(req, authorization=None))
        self.assertEqual(ctx.exception.status_code, 401)

    def test_bearer_header_is_accepted(self) -> None:
        req = _request({"authorization": "Bearer secret-key"})
        ctx = asyncio.run(auth_mod.verify_api_key(req, authorization="Bearer secret-key"))
        self.assertEqual(ctx.identity, "static-api-key")

    def test_x_api_key_header_is_accepted(self) -> None:
        req = _request({"X-API-Key": "secret-key"})
        ctx = asyncio.run(auth_mod.verify_api_key(req, authorization=None))
        self.assertEqual(ctx.identity, "static-api-key")


class TestHashedTokens(_TempStoreMixin, unittest.TestCase):
    def test_raw_tokens_are_never_stored(self) -> None:
        asyncio.run(self.store.store_tokens("acc-raw", "ref-raw", "client-a"))
        asyncio.run(self.store.store_auth_code("code-raw", "client-a"))
        stored = {r[0] for r in self._rows("SELECT token FROM access_tokens")}
        stored |= {r[0] for r in self._rows("SELECT token FROM refresh_tokens")}
        stored |= {r[0] for r in self._rows("SELECT code FROM auth_codes")}
        self.assertEqual(stored, {_sha256("acc-raw"), _sha256("ref-raw"), _sha256("code-raw")})

    def test_lookups_work_with_raw_values(self) -> None:
        asyncio.run(self.store.store_tokens("acc-raw", "ref-raw", "client-a"))
        asyncio.run(self.store.store_auth_code("code-raw", "client-a"))
        self.assertEqual(asyncio.run(self.store.get_access_token("acc-raw"))["client_id"], "client-a")
        self.assertEqual(asyncio.run(self.store.get_refresh_token("ref-raw"))["client_id"], "client-a")
        self.assertEqual(asyncio.run(self.store.get_auth_code("code-raw"))["client_id"], "client-a")
        asyncio.run(self.store.delete_auth_code("code-raw"))
        self.assertIsNone(asyncio.run(self.store.get_auth_code("code-raw")))

    def test_rotation_keeps_working(self) -> None:
        asyncio.run(self.store.store_tokens("acc-raw", "ref-raw", "client-a"))
        new_access, new_refresh = asyncio.run(self.store.rotate_refresh_token("ref-raw"))
        self.assertIsNone(asyncio.run(self.store.get_refresh_token("ref-raw")))
        self.assertIsNotNone(asyncio.run(self.store.get_access_token(new_access)))
        self.assertIsNotNone(asyncio.run(self.store.get_refresh_token(new_refresh)))
        self.assertNotIn(
            new_refresh, {r[0] for r in self._rows("SELECT token FROM refresh_tokens")}
        )

    def test_legacy_raw_rows_are_migrated_once(self) -> None:
        legacy_dir = tempfile.TemporaryDirectory()
        path = os.path.join(legacy_dir.name, "tokens.db")
        conn = sqlite3.connect(path)
        conn.executescript(
            """
            CREATE TABLE access_tokens (token TEXT PRIMARY KEY, client_id TEXT NOT NULL, scope TEXT, expires_at INTEGER NOT NULL);
            CREATE TABLE refresh_tokens (token TEXT PRIMARY KEY, client_id TEXT NOT NULL, scope TEXT, expires_at INTEGER NOT NULL);
            CREATE TABLE auth_codes (code TEXT PRIMARY KEY, client_id TEXT NOT NULL, redirect_uri TEXT, code_challenge TEXT, scope TEXT, expires_at INTEGER NOT NULL);
            INSERT INTO access_tokens VALUES ('legacy-acc', 'claude', 'mcp', 9999999999);
            INSERT INTO refresh_tokens VALUES ('legacy-ref', 'claude', 'mcp', 9999999999);
            """
        )
        conn.commit()
        conn.close()
        try:
            store = TokenStore(db_path=path)
            asyncio.run(store.init_db())
            asyncio.run(store.init_db())  # second start (or second worker) must not re-hash
            self.assertIsNotNone(asyncio.run(store.get_access_token("legacy-acc")))
            self.assertIsNotNone(asyncio.run(store.get_refresh_token("legacy-ref")))
            conn = sqlite3.connect(path)
            raw = conn.execute(
                "SELECT COUNT(*) FROM access_tokens WHERE token = 'legacy-acc'"
            ).fetchone()[0]
            conn.close()
            self.assertEqual(raw, 0)
        finally:
            legacy_dir.cleanup()


class TestRevokeEndpoint(_TempStoreMixin, unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.client = TestClient(main.app)
        asyncio.run(self.store.store_tokens("acc-a", "ref-a", "client-a"))

    def test_metadata_advertises_revocation(self) -> None:
        body = self.client.get("/.well-known/oauth-authorization-server").json()
        self.assertTrue(body["revocation_endpoint"].endswith("/revoke"))
        self.assertEqual(body["revocation_endpoint_auth_methods_supported"], ["none"])

    def test_revoke_refresh_token(self) -> None:
        r = self.client.post("/revoke", data={"token": "ref-a", "client_id": "client-a"})
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(asyncio.run(self.store.get_refresh_token("ref-a")))

    def test_revoke_access_token(self) -> None:
        r = self.client.post(
            "/revoke",
            data={"token": "acc-a", "client_id": "client-a", "token_type_hint": "access_token"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(asyncio.run(self.store.get_access_token("acc-a")))

    def test_other_client_cannot_revoke(self) -> None:
        r = self.client.post("/revoke", data={"token": "ref-a", "client_id": "client-b"})
        self.assertEqual(r.status_code, 200)  # RFC 7009: no information leak
        self.assertIsNotNone(asyncio.run(self.store.get_refresh_token("ref-a")))

    def test_unknown_token_is_200(self) -> None:
        r = self.client.post("/revoke", data={"token": "nope", "client_id": "client-a"})
        self.assertEqual(r.status_code, 200)

    def test_missing_fields_is_400(self) -> None:
        self.assertEqual(self.client.post("/revoke", data={"client_id": "client-a"}).status_code, 400)
        self.assertEqual(self.client.post("/revoke", data={"token": "ref-a"}).status_code, 400)


class TestStrictAuthorize(_TempStoreMixin, unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.client = TestClient(main.app)

    def _authorize(self, resolved, **params):
        query = {"response_type": "code", "client_id": "some-client",
                 "code_challenge": "abc", "code_challenge_method": "S256"}
        query.update(params)
        with patch("main.resolve_oauth_client", new=AsyncMock(return_value=resolved)):
            return self.client.get("/authorize", params=query, follow_redirects=False)

    def test_unknown_client_without_redirect_is_rejected(self) -> None:
        r = self._authorize(None)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self._rows("SELECT COUNT(*) FROM auth_codes")[0][0], 0)

    def test_unknown_client_with_redirect_is_rejected(self) -> None:
        r = self._authorize(None, redirect_uri="https://example.com/cb")
        self.assertEqual(r.status_code, 400)

    def test_known_client_without_redirect_uses_its_only_uri(self) -> None:
        resolved = {"client_id": "some-client", "redirect_uris": ["https://example.com/cb"], "source": "dcr"}
        r = self._authorize(resolved)
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["location"].startswith("https://example.com/cb?code="))

    def test_known_client_with_several_uris_must_choose(self) -> None:
        resolved = {"client_id": "some-client", "source": "dcr",
                    "redirect_uris": ["https://a.example/cb", "https://b.example/cb"]}
        r = self._authorize(resolved)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self._rows("SELECT COUNT(*) FROM auth_codes")[0][0], 0)


class TestRevokeCli(_TempStoreMixin, unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        from scripts import revoke_tokens

        self.cli = revoke_tokens
        asyncio.run(self.store.store_tokens("acc-a", "ref-a", "client-a"))
        asyncio.run(self.store.store_tokens("acc-b", "ref-b", "client-b"))

    def test_lists_clients(self) -> None:
        rows = {cid: (a, r) for cid, a, r in self.cli.list_clients(self.db_path)}
        self.assertEqual(rows, {"client-a": (1, 1), "client-b": (1, 1)})

    def test_needs_yes(self) -> None:
        self.assertEqual(self.cli.main(["--db", self.db_path, "--all"]), 2)
        self.assertEqual(len(self.cli.list_clients(self.db_path)), 2)

    def test_revoke_one_client(self) -> None:
        self.assertEqual(self.cli.main(["--db", self.db_path, "--client", "client-a", "--yes"]), 0)
        self.assertIsNone(asyncio.run(self.store.get_refresh_token("ref-a")))
        self.assertIsNotNone(asyncio.run(self.store.get_refresh_token("ref-b")))

    def test_revoke_all(self) -> None:
        self.assertEqual(self.cli.main(["--db", self.db_path, "--all", "--yes"]), 0)
        self.assertEqual(self.cli.list_clients(self.db_path), [])


class TestScopedKeyExcludesWork(unittest.TestCase):
    """A Gravity-style key without `work` can neither read nor write the work workspace."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        path = os.path.join(self._tmpdir.name, "workspace_keys.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"keys": {"gravity-key": {
                "name": "Gravity", "role": "user",
                "scopes": ["personal", "passion", "parallax", "spectrum"],
                "write_scopes": ["personal"],
            }}}, f)
        self._env = patch.dict(os.environ, {"WORKSPACE_KEYS_PATH": path, "MCP_REQUIRE_AUTH": "true"})
        self._env.start()
        auth_mod.clear_workspace_config_cache()
        req = _request({"authorization": "Bearer gravity-key"})
        self.ctx = asyncio.run(auth_mod.verify_api_key(req, authorization="Bearer gravity-key"))

    def tearDown(self) -> None:
        self._env.stop()
        auth_mod.clear_workspace_config_cache()
        self._tmpdir.cleanup()

    def test_work_not_in_scopes(self) -> None:
        self.assertNotIn("work", self.ctx.allowed_scopes)
        self.assertNotIn("work", self.ctx.effective_write_scopes)

    def test_work_read_denied(self) -> None:
        with self.assertRaises(PermissionError):
            active_scopes_for_read("work", self.ctx.allowed_scopes)
        with self.assertRaises(PermissionError):
            resolve_scoped_path("11_meeting-notes/x.md", "work", self.ctx.allowed_scopes)

    def test_work_write_denied(self) -> None:
        with self.assertRaises(PermissionError):
            resolve_write_scope("work", self.ctx.effective_write_scopes)

    def test_default_read_never_includes_work(self) -> None:
        self.assertNotIn("work", active_scopes_for_read(None, self.ctx.allowed_scopes))


if __name__ == "__main__":
    unittest.main()
