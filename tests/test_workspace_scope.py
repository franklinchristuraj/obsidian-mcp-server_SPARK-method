"""Unit tests for workspace scope helpers (stdlib unittest)."""
import asyncio
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock

from src.scope import (
    WorkspaceContext,
    active_scopes_for_read,
    forbid_scope_prefix_in_agent_path,
    parse_default_workspace_scopes,
    resolve_scoped_path,
    resolve_write_scope,
    scoped_list_folder,
    strip_scope_prefix,
)
from src import auth as auth_mod


class TestScopeHelpers(unittest.TestCase):
    def test_resolve_scoped_path(self) -> None:
        self.assertEqual(
            resolve_scoped_path("01_seeds/x.md", "personal", ("personal", "work")),
            "personal/01_seeds/x.md",
        )

    def test_resolve_scoped_path_denies_bad_scope(self) -> None:
        with self.assertRaises(PermissionError):
            resolve_scoped_path("a.md", "work", ("personal",))

    def test_forbid_scope_prefix(self) -> None:
        with self.assertRaises(ValueError):
            forbid_scope_prefix_in_agent_path("personal/01_seeds/x.md")

    def test_resolve_write_scope_single(self) -> None:
        self.assertEqual(
            resolve_write_scope(None, ("work",)),
            "work",
        )
        self.assertEqual(
            resolve_write_scope("work", ("work",)),
            "work",
        )

    def test_resolve_write_scope_multi_requires_param(self) -> None:
        with self.assertRaises(ValueError):
            resolve_write_scope(None, ("personal", "passion"))

    def test_active_scopes_for_read(self) -> None:
        self.assertEqual(
            active_scopes_for_read(None, ("personal", "work")),
            ["personal", "work"],
        )
        self.assertEqual(
            active_scopes_for_read("work", ("personal", "work")),
            ["work"],
        )

    def test_strip_scope_prefix(self) -> None:
        rel, sc = strip_scope_prefix(
            "personal/06_daily-notes/2026-04-11.md", ("personal", "work")
        )
        self.assertEqual(sc, "personal")
        self.assertEqual(rel, "06_daily-notes/2026-04-11.md")

    def test_scoped_list_folder(self) -> None:
        self.assertEqual(scoped_list_folder("", "passion"), "passion")
        self.assertEqual(
            scoped_list_folder("03_areas", "passion"),
            "passion/03_areas",
        )


class TestWorkspaceKeysAuth(unittest.TestCase):
    def setUp(self) -> None:
        auth_mod.clear_workspace_config_cache()

    def tearDown(self) -> None:
        auth_mod.clear_workspace_config_cache()

    def test_static_key_uses_json_scopes(self) -> None:
        cfg = {
            "keys": {
                "secret-one": {
                    "name": "Work",
                    "scopes": ["work"],
                    "role": "user",
                }
            }
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as tmp:
            json.dump(cfg, tmp)
            path = tmp.name
        try:
            os.environ["WORKSPACE_KEYS_PATH"] = path
            os.environ["MCP_API_KEY"] = "secret-one"
            os.environ["MCP_REQUIRE_AUTH"] = "true"

            async def run() -> WorkspaceContext:
                req = MagicMock()
                req.query_params.get.return_value = None
                req.headers.get.return_value = None
                req.headers = {"authorization": "Bearer secret-one"}
                return await auth_mod.verify_api_key(
                    req, authorization="Bearer secret-one"
                )

            ctx = asyncio.run(run())
            self.assertEqual(ctx.allowed_scopes, ("work",))
            self.assertEqual(ctx.role, "user")
        finally:
            os.unlink(path)
            os.environ.pop("WORKSPACE_KEYS_PATH", None)
            os.environ.pop("MCP_API_KEY", None)
            os.environ.pop("MCP_REQUIRE_AUTH", None)


class TestTemplateScopePrefix(unittest.TestCase):
    def test_template_path_prefix(self) -> None:
        from src.utils.template_utils import template_detector

        p = template_detector.get_template_path_for_folder(
            "01_seeds/idea.md", workspace_scope="personal"
        )
        self.assertTrue(p.startswith("personal/"))
        self.assertIn("templates", p)


class TestObsidianRoutedNames(unittest.TestCase):
    def test_search_routed(self) -> None:
        from src.tools.obsidian_tools import OBSIDIAN_ROUTED_TOOL_NAMES

        self.assertIn("search", OBSIDIAN_ROUTED_TOOL_NAMES)
        self.assertIn("workspaces", OBSIDIAN_ROUTED_TOOL_NAMES)
        self.assertNotIn("obs_search_notes", OBSIDIAN_ROUTED_TOOL_NAMES)
        self.assertNotIn("obs_execute_command", OBSIDIAN_ROUTED_TOOL_NAMES)


if __name__ == "__main__":
    unittest.main()
