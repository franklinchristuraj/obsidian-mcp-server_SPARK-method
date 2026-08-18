"""Client ID Metadata Documents (CIMD) — fetch-on-demand OAuth client identity.

When client_id is an HTTPS URL, fetch and validate the metadata document
(SEP-991). Opaque DCR client_ids continue to use token_store.
"""
from __future__ import annotations

import ipaddress
import json
import os
import socket
import sqlite3
import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx

CIMD_CACHE_DB = os.getenv("CIMD_CACHE_DB", "cimd_cache.db")
CIMD_TTL_SECONDS = int(os.getenv("CIMD_CACHE_TTL_SECONDS", "86400"))
CIMD_FETCH_TIMEOUT = float(os.getenv("CIMD_FETCH_TIMEOUT", "5.0"))
CIMD_MAX_BYTES = int(os.getenv("CIMD_MAX_BYTES", "65536"))


def is_cimd_client_id(client_id: str) -> bool:
    return client_id.startswith("https://")


def _is_public_hostname(hostname: str) -> bool:
    """Reject hostnames that resolve only to private/link-local addresses."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False
    if not infos:
        return False
    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    return True


class CimdError(Exception):
    """Client metadata fetch/validation failure."""


def _ensure_cache_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS cimd_cache (
            url TEXT PRIMARY KEY,
            body_json TEXT NOT NULL,
            fetched_at REAL NOT NULL
        );
        """
    )
    conn.commit()


def _cache_get(url: str) -> Optional[Dict[str, Any]]:
    conn = sqlite3.connect(CIMD_CACHE_DB)
    try:
        _ensure_cache_schema(conn)
        row = conn.execute(
            "SELECT body_json, fetched_at FROM cimd_cache WHERE url = ?", (url,)
        ).fetchone()
        if row is None:
            return None
        body_json, fetched_at = row
        if time.time() - float(fetched_at) > CIMD_TTL_SECONDS:
            return None
        return json.loads(body_json)
    finally:
        conn.close()


def _cache_put(url: str, doc: Dict[str, Any]) -> None:
    conn = sqlite3.connect(CIMD_CACHE_DB)
    try:
        _ensure_cache_schema(conn)
        conn.execute(
            """INSERT OR REPLACE INTO cimd_cache (url, body_json, fetched_at)
               VALUES (?, ?, ?)""",
            (url, json.dumps(doc), time.time()),
        )
        conn.commit()
    finally:
        conn.close()


async def fetch_cimd(client_id: str) -> Dict[str, Any]:
    """Fetch and validate a CIMD document. Raises CimdError on failure."""
    if not is_cimd_client_id(client_id):
        raise CimdError("client_id is not an HTTPS CIMD URL")

    parsed = urlparse(client_id)
    if parsed.scheme != "https" or not parsed.hostname:
        raise CimdError("CIMD client_id must be an https URL with a hostname")
    if parsed.username or parsed.password:
        raise CimdError("CIMD URL must not include credentials")
    if not _is_public_hostname(parsed.hostname):
        raise CimdError("CIMD host resolves to a non-public address (SSRF blocked)")

    cached = _cache_get(client_id)
    if cached is not None:
        return cached

    try:
        async with httpx.AsyncClient(
            timeout=CIMD_FETCH_TIMEOUT,
            follow_redirects=False,
            max_redirects=0,
        ) as client:
            resp = await client.get(
                client_id,
                headers={"Accept": "application/json"},
            )
    except httpx.HTTPError as e:
        raise CimdError(f"CIMD fetch failed: {e}") from e

    if resp.status_code != 200:
        raise CimdError(f"CIMD fetch returned HTTP {resp.status_code}")
    if len(resp.content) > CIMD_MAX_BYTES:
        raise CimdError("CIMD document exceeds size limit")

    try:
        doc = resp.json()
    except json.JSONDecodeError as e:
        raise CimdError("CIMD document is not valid JSON") from e
    if not isinstance(doc, dict):
        raise CimdError("CIMD document must be a JSON object")

    # client_id inside the document must match the URL used to fetch it
    doc_id = doc.get("client_id")
    if doc_id is not None and doc_id != client_id:
        raise CimdError("CIMD client_id field does not match document URL")

    redirect_uris = doc.get("redirect_uris")
    if not isinstance(redirect_uris, list) or not redirect_uris:
        raise CimdError("CIMD document missing redirect_uris")

    if "client_name" not in doc:
        doc = {**doc, "client_name": parsed.hostname}

    _cache_put(client_id, doc)
    return doc


async def resolve_oauth_client(
    client_id: str,
    *,
    get_dcr_client,
) -> Optional[Dict[str, Any]]:
    """
    Resolve client metadata from CIMD (HTTPS URL) or DCR store.

    Returns a dict with at least: client_id, client_name, redirect_uris.
    """
    if is_cimd_client_id(client_id):
        doc = await fetch_cimd(client_id)
        return {
            "client_id": client_id,
            "client_name": doc.get("client_name") or client_id,
            "redirect_uris": list(doc.get("redirect_uris") or []),
            "grant_types": doc.get("grant_types")
            or ["authorization_code", "refresh_token"],
            "response_types": doc.get("response_types") or ["code"],
            "token_endpoint_auth_method": doc.get("token_endpoint_auth_method")
            or "none",
            "source": "cimd",
        }

    dcr = await get_dcr_client(client_id)
    if dcr is None:
        return None
    return {**dcr, "source": "dcr"}
