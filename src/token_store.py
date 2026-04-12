"""
SQLite-backed token store for OAuth 2.0 with refresh token support.

Tables:
  auth_codes    -- short-lived auth codes (TTL: 10 min)
  access_tokens -- short-lived access tokens (TTL: 1 hour)
  refresh_tokens -- long-lived refresh tokens (TTL: 30 days)
"""
import asyncio
import base64
import hashlib
import secrets
import sqlite3
import time
from typing import Optional


class TokenStore:
    def __init__(self, db_path: str = "tokens.db"):
        self.db_path = db_path
        self._lock = asyncio.Lock()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    async def init_db(self) -> None:
        """Create tables if they don't exist."""
        async with self._lock:
            conn = self._get_conn()
            try:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS oauth_clients (
                        client_id TEXT PRIMARY KEY,
                        client_name TEXT,
                        redirect_uris TEXT NOT NULL,
                        grant_types TEXT,
                        response_types TEXT,
                        token_endpoint_auth_method TEXT DEFAULT 'none',
                        created_at INTEGER NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS auth_codes (
                        code TEXT PRIMARY KEY,
                        client_id TEXT NOT NULL,
                        redirect_uri TEXT,
                        code_challenge TEXT,
                        scope TEXT,
                        expires_at INTEGER NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS access_tokens (
                        token TEXT PRIMARY KEY,
                        client_id TEXT NOT NULL,
                        scope TEXT,
                        expires_at INTEGER NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS refresh_tokens (
                        token TEXT PRIMARY KEY,
                        client_id TEXT NOT NULL,
                        scope TEXT,
                        expires_at INTEGER NOT NULL
                    );
                """)
                # Migrate: add redirect_uri column to auth_codes if missing
                cursor = conn.execute("PRAGMA table_info(auth_codes)")
                columns = [row[1] for row in cursor.fetchall()]
                if "redirect_uri" not in columns:
                    conn.execute("ALTER TABLE auth_codes ADD COLUMN redirect_uri TEXT")

                conn.commit()
            finally:
                conn.close()

    # -------------------------------------------------------------------------
    # OAuth clients (Dynamic Client Registration - RFC 7591)
    # -------------------------------------------------------------------------

    async def register_client(
        self,
        client_name: str,
        redirect_uris: list[str],
        grant_types: list[str] | None = None,
        response_types: list[str] | None = None,
        token_endpoint_auth_method: str = "none",
    ) -> dict:
        """Register a new OAuth client. Returns the full client record."""
        import json as _json

        client_id = secrets.token_urlsafe(24)
        now = int(time.time())
        grant_types = grant_types or ["authorization_code", "refresh_token"]
        response_types = response_types or ["code"]

        async with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT INTO oauth_clients (client_id, client_name, redirect_uris, grant_types, response_types, token_endpoint_auth_method, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        client_id,
                        client_name,
                        _json.dumps(redirect_uris),
                        _json.dumps(grant_types),
                        _json.dumps(response_types),
                        token_endpoint_auth_method,
                        now,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

        return {
            "client_id": client_id,
            "client_name": client_name,
            "redirect_uris": redirect_uris,
            "grant_types": grant_types,
            "response_types": response_types,
            "token_endpoint_auth_method": token_endpoint_auth_method,
        }

    async def get_client(self, client_id: str) -> Optional[dict]:
        """Return client data, or None if not found."""
        import json as _json

        async with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM oauth_clients WHERE client_id = ?", (client_id,)
                ).fetchone()
                if row is None:
                    return None
                data = dict(row)
                data["redirect_uris"] = _json.loads(data["redirect_uris"])
                data["grant_types"] = _json.loads(data["grant_types"])
                data["response_types"] = _json.loads(data["response_types"])
                return data
            finally:
                conn.close()

    # -------------------------------------------------------------------------
    # Auth codes
    # -------------------------------------------------------------------------

    async def store_auth_code(
        self,
        code: str,
        client_id: str,
        redirect_uri: Optional[str] = None,
        code_challenge: Optional[str] = None,
        scope: Optional[str] = None,
    ) -> None:
        expires_at = int(time.time()) + 600  # 10 minutes
        async with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO auth_codes (code, client_id, redirect_uri, code_challenge, scope, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (code, client_id, redirect_uri, code_challenge, scope, expires_at),
                )
                conn.commit()
            finally:
                conn.close()

    async def get_auth_code(self, code: str) -> Optional[dict]:
        """Return auth code data, or None if not found / expired."""
        async with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM auth_codes WHERE code = ? AND expires_at > ?",
                    (code, int(time.time())),
                ).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

    async def delete_auth_code(self, code: str) -> None:
        """Consume an auth code (single-use)."""
        async with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("DELETE FROM auth_codes WHERE code = ?", (code,))
                conn.commit()
            finally:
                conn.close()

    # -------------------------------------------------------------------------
    # Access + refresh tokens
    # -------------------------------------------------------------------------

    async def store_tokens(
        self,
        access_token: str,
        refresh_token: str,
        client_id: str,
        scope: Optional[str] = None,
    ) -> None:
        now = int(time.time())
        access_expires = now + 3600         # 1 hour
        refresh_expires = now + 30 * 86400  # 30 days
        async with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO access_tokens (token, client_id, scope, expires_at) VALUES (?, ?, ?, ?)",
                    (access_token, client_id, scope, access_expires),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO refresh_tokens (token, client_id, scope, expires_at) VALUES (?, ?, ?, ?)",
                    (refresh_token, client_id, scope, refresh_expires),
                )
                conn.commit()
            finally:
                conn.close()

    async def get_access_token(self, token: str) -> Optional[dict]:
        """Return access token data, or None if not found / expired."""
        async with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM access_tokens WHERE token = ? AND expires_at > ?",
                    (token, int(time.time())),
                ).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

    async def get_refresh_token(self, token: str) -> Optional[dict]:
        """Return refresh token data, or None if not found / expired."""
        async with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM refresh_tokens WHERE token = ? AND expires_at > ?",
                    (token, int(time.time())),
                ).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

    async def rotate_refresh_token(
        self, old_refresh_token: str
    ) -> tuple[str, str]:
        """
        Rotate a refresh token: revoke old pair, issue new access + refresh tokens.
        Returns (new_access_token, new_refresh_token).
        Raises ValueError if old token is invalid or expired.
        """
        token_data = await self.get_refresh_token(old_refresh_token)
        if token_data is None:
            raise ValueError("Refresh token invalid or expired")

        client_id = token_data["client_id"]
        scope = token_data["scope"]

        new_access = secrets.token_urlsafe(32)
        new_refresh = secrets.token_urlsafe(32)

        async with self._lock:
            conn = self._get_conn()
            try:
                # Revoke old refresh token
                conn.execute(
                    "DELETE FROM refresh_tokens WHERE token = ?", (old_refresh_token,)
                )
                now = int(time.time())
                conn.execute(
                    "INSERT OR REPLACE INTO access_tokens (token, client_id, scope, expires_at) VALUES (?, ?, ?, ?)",
                    (new_access, client_id, scope, now + 3600),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO refresh_tokens (token, client_id, scope, expires_at) VALUES (?, ?, ?, ?)",
                    (new_refresh, client_id, scope, now + 30 * 86400),
                )
                conn.commit()
            finally:
                conn.close()

        return new_access, new_refresh

    async def revoke_access_token(self, token: str) -> None:
        async with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("DELETE FROM access_tokens WHERE token = ?", (token,))
                conn.commit()
            finally:
                conn.close()

    # -------------------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------------------

    async def cleanup_expired(self) -> None:
        """Delete expired tokens from all tables."""
        now = int(time.time())
        async with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("DELETE FROM auth_codes WHERE expires_at <= ?", (now,))
                conn.execute("DELETE FROM access_tokens WHERE expires_at <= ?", (now,))
                conn.execute("DELETE FROM refresh_tokens WHERE expires_at <= ?", (now,))
                conn.commit()
            finally:
                conn.close()


# -------------------------------------------------------------------------
# PKCE helpers
# -------------------------------------------------------------------------

def generate_token() -> str:
    return secrets.token_urlsafe(32)


def verify_pkce(code_challenge: str, code_verifier: str) -> bool:
    """
    Verify PKCE S256 challenge.
    code_challenge == base64url(sha256(code_verifier))
    """
    digest = hashlib.sha256(code_verifier.encode()).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return expected == code_challenge
