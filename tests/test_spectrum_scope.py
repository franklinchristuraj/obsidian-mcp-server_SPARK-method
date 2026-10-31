"""Spectrum scope registration: known scope, defaults, templates, key fence."""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src import auth as auth_mod
from src.scope import (
    KNOWN_SCOPES,
    WorkspaceContext,
    forbid_scope_prefix_in_agent_path,
    parse_default_workspace_scopes,
    resolve_scoped_path,
)
from src.utils.template_utils import template_detector


class TestSpectrumKnownScopes(unittest.TestCase):
    def test_known_scopes_include_spectrum(self) -> None:
        self.assertIn("spectrum", KNOWN_SCOPES)
        self.assertEqual(KNOWN_SCOPES[-1], "spectrum")

    def test_default_env_includes_spectrum(self) -> None:
        os.environ.pop("MCP_DEFAULT_WORKSPACE_SCOPES", None)
        scopes = parse_default_workspace_scopes()
        self.assertIn("spectrum", scopes)

    def test_resolve_and_forbid_prefix(self) -> None:
        self.assertEqual(
            resolve_scoped_path(
                "01_insights/claim.md", "spectrum", ("spectrum",)
            ),
            "spectrum/01_insights/claim.md",
        )
        with self.assertRaises(ValueError):
            forbid_scope_prefix_in_agent_path("spectrum/01_insights/claim.md")
        with self.assertRaises(PermissionError):
            resolve_scoped_path(
                "01_insights/claim.md", "spectrum", ("passion",)
            )

    def test_template_paths(self) -> None:
        cases = {
            "01_insights/claim.md": "spectrum/00_system/templates/insight.md",
            "02_frameworks/model.md": "spectrum/00_system/templates/framework.md",
            "04_pieces/loop-interrupted/li-e01-x.md": (
                "spectrum/00_system/templates/episode.md"
            ),
            "04_pieces/youtube/2026-10-26_x.md": (
                "spectrum/00_system/templates/video.md"
            ),
            "04_pieces/instagram/2026-10-26_reel.md": (
                "spectrum/00_system/templates/social-post.md"
            ),
            "04_pieces/linkedin/2026-10-26_post.md": (
                "spectrum/00_system/templates/linkedin-post.md"
            ),
        }
        for path, expected in cases.items():
            self.assertEqual(
                template_detector.get_template_path_for_folder(
                    path, workspace_scope="spectrum"
                ),
                expected,
                msg=path,
            )


class TestSpectrumKeyFence(unittest.TestCase):
    def setUp(self) -> None:
        auth_mod.clear_workspace_config_cache()

    def tearDown(self) -> None:
        auth_mod.clear_workspace_config_cache()

    def _context_for(self, cfg: dict, token: str) -> WorkspaceContext:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as tmp:
            json.dump(cfg, tmp)
            path = tmp.name
        env = {
            "WORKSPACE_KEYS_PATH": path,
            "MCP_API_KEY": token,
            "MCP_REQUIRE_AUTH": "true",
        }
        try:
            with patch.dict(os.environ, env):
                auth_mod.clear_workspace_config_cache()

                async def run() -> WorkspaceContext:
                    req = MagicMock()
                    req.query_params.get.return_value = None
                    req.headers.get.return_value = None
                    req.headers = {"authorization": f"Bearer {token}"}
                    return await auth_mod.verify_api_key(
                        req, authorization=f"Bearer {token}"
                    )

                return asyncio.run(run())
        finally:
            os.unlink(path)

    def test_full_key_can_read_and_write_spectrum(self) -> None:
        cfg = {
            "keys": {
                "admin-key": {
                    "name": "Admin",
                    "scopes": [
                        "personal",
                        "passion",
                        "work",
                        "parallax",
                        "spectrum",
                    ],
                    "role": "admin",
                }
            }
        }
        ctx = self._context_for(cfg, "admin-key")
        self.assertIn("spectrum", ctx.allowed_scopes)
        self.assertIn("spectrum", ctx.effective_write_scopes)

    def test_narrow_key_does_not_gain_spectrum(self) -> None:
        cfg = {
            "keys": {
                "passion-key": {
                    "name": "Passion agent",
                    "scopes": ["passion"],
                    "role": "agent",
                }
            }
        }
        ctx = self._context_for(cfg, "passion-key")
        self.assertEqual(ctx.allowed_scopes, ("passion",))
        self.assertNotIn("spectrum", ctx.effective_write_scopes)
