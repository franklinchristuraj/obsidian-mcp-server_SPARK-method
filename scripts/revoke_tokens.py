#!/usr/bin/env python3
"""
List or revoke OAuth tokens in the token store ("my laptop was stolen").

Usage (from the server checkout, so TOKEN_DB_PATH in .env resolves):
    venv/bin/python scripts/revoke_tokens.py                    # list clients holding tokens
    venv/bin/python scripts/revoke_tokens.py --client <id> --yes
    venv/bin/python scripts/revoke_tokens.py --all --yes        # every client must log in again

Revoked clients must go through /authorize again. Static keys in
workspace_keys.json are not affected; remove or rotate those by hand.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from typing import List, Optional, Tuple

_TABLES = ("access_tokens", "refresh_tokens")


def list_clients(db_path: str) -> List[Tuple[str, int, int]]:
    """(client_id, live access tokens, live refresh tokens), most tokens first."""
    now = int(time.time())
    conn = sqlite3.connect(db_path)
    try:
        counts: dict[str, list[int]] = {}
        for i, table in enumerate(_TABLES):
            for client_id, n in conn.execute(
                f"SELECT client_id, COUNT(*) FROM {table} WHERE expires_at > ? GROUP BY client_id",
                (now,),
            ):
                counts.setdefault(client_id, [0, 0])[i] = n
        return sorted(
            ((cid, a, r) for cid, (a, r) in counts.items()),
            key=lambda row: -(row[1] + row[2]),
        )
    finally:
        conn.close()


def revoke(db_path: str, client_id: Optional[str]) -> int:
    """Delete tokens for one client, or for every client when client_id is None."""
    conn = sqlite3.connect(db_path)
    try:
        deleted = 0
        for table in _TABLES:
            if client_id is None:
                deleted += conn.execute(f"DELETE FROM {table}").rowcount
            else:
                deleted += conn.execute(
                    f"DELETE FROM {table} WHERE client_id = ?", (client_id,)
                ).rowcount
        conn.commit()
        return deleted
    finally:
        conn.close()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--client", help="client_id to revoke")
    target.add_argument("--all", action="store_true", help="revoke every client")
    parser.add_argument("--yes", action="store_true", help="confirm revocation")
    parser.add_argument("--db", help="token DB path (default: TOKEN_DB_PATH or tokens.db)")
    args = parser.parse_args(argv)

    if args.db:
        db_path = args.db
    else:
        try:
            from dotenv import load_dotenv

            load_dotenv(".env")
        except ImportError:
            pass
        db_path = os.getenv("TOKEN_DB_PATH", "tokens.db")
    if not os.path.isfile(db_path):
        print(f"Token DB not found: {db_path}", file=sys.stderr)
        return 1

    if not args.client and not args.all:
        rows = list_clients(db_path)
        if not rows:
            print("No live OAuth tokens.")
        for client_id, access, refresh in rows:
            print(f"{client_id}\taccess={access}\trefresh={refresh}")
        return 0

    if not args.yes:
        what = "ALL clients" if args.all else args.client
        print(f"Would revoke tokens for {what}. Re-run with --yes to do it.")
        return 2

    deleted = revoke(db_path, None if args.all else args.client)
    print(f"Revoked {deleted} token(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
