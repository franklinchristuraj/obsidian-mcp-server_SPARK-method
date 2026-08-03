"""MCP Apps transport + registry tests."""
from __future__ import annotations

import unittest

from src.apps.registry import (
    APP_TOOL_NAMES,
    get_app_tools,
    list_ui_app_resources,
    read_ui_app_resource,
)
from src.apps.paths import base_ui_uri, bundle_version, split_ui_uri
from src.apps.paths import ui_uri as path_ui_uri
from src.mcp_server import MCPProtocolHandler
from src.apps.composers.prep_card import staleness_band


class TestMcpAppsTransport(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.handler = MCPProtocolHandler()

    async def test_initialize_declares_ui_extension(self) -> None:
        result = await self.handler._handle_initialize(
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {
                    "extensions": {
                        "io.modelcontextprotocol/ui": {
                            "mimeTypes": ["text/html;profile=mcp-app"]
                        }
                    }
                },
                "clientInfo": {"name": "test", "version": "0"},
            }
        )
        caps = result["capabilities"]
        self.assertIn("extensions", caps)
        self.assertIn("io.modelcontextprotocol/ui", caps["extensions"])
        self.assertEqual(
            self.handler.client_capabilities.get("extensions", {})
            .get("io.modelcontextprotocol/ui", {})
            .get("mimeTypes"),
            ["text/html;profile=mcp-app"],
        )

    async def test_tools_list_preserves_meta(self) -> None:
        result = await self.handler._handle_tools_list({})
        by_name = {t["name"]: t for t in result["tools"]}
        self.assertIn("prep_card", by_name)
        meta = by_name["prep_card"].get("_meta")
        self.assertIsNotNone(meta)
        resource_uri = meta["ui"]["resourceUri"]
        self.assertTrue(resource_uri.startswith("ui://ziksaka/prep-card@"))
        self.assertEqual(split_ui_uri(resource_uri)[0], "prep-card")
        self.assertIn("model", meta["ui"]["visibility"])

        lint_apply = by_name["lint_apply"]
        self.assertEqual(lint_apply["_meta"]["ui"]["visibility"], ["app"])

    async def test_ui_resources_list_and_read(self) -> None:
        resources = list_ui_app_resources()
        apps = {split_ui_uri(r.uri)[0] for r in resources}
        self.assertIn("smoke", apps)
        self.assertIn("prep-card", apps)
        for r in resources:
            self.assertEqual(r.mimeType, "text/html;profile=mcp-app")
            self.assertIn("ui", (r.meta or {}))
            # Every advertised URI carries a cache-busting version.
            self.assertIsNotNone(split_ui_uri(r.uri)[1])

        content = read_ui_app_resource(path_ui_uri("smoke"))
        self.assertIn("<!DOCTYPE html>", content["text"])
        self.assertEqual(content["mimeType"], "text/html;profile=mcp-app")
        self.assertIn("csp", content["metadata"]["ui"])

    async def test_read_accepts_unversioned_and_stale_versions(self) -> None:
        """Version is cache-busting only; it must not gate reads."""
        for uri in (
            "ui://ziksaka/smoke",
            "ui://ziksaka/smoke@deadbeefcafe",
            path_ui_uri("smoke"),
        ):
            content = read_ui_app_resource(uri)
            self.assertIn("<!DOCTYPE html>", content["text"])

        with self.assertRaises(ValueError):
            read_ui_app_resource("ui://ziksaka/not-an-app@v1")
        with self.assertRaises(ValueError):
            read_ui_app_resource("https://example.com/smoke")

    def test_version_tracks_bundle_content(self) -> None:
        version = bundle_version("smoke")
        self.assertEqual(len(version), 12)
        self.assertEqual(bundle_version("smoke"), version)
        self.assertNotEqual(bundle_version("prep-card"), version)
        self.assertEqual(path_ui_uri("smoke"), f"{base_ui_uri('smoke')}@{version}")

    async def test_smoke_tool_call(self) -> None:
        result = await self.handler._handle_tools_call(
            {"name": "mcp_apps_smoke", "arguments": {}}
        )
        self.assertIn("structuredContent", result)
        self.assertTrue(result["structuredContent"].get("ok"))

    def test_app_tool_count(self) -> None:
        tools = get_app_tools()
        self.assertEqual({t.name for t in tools}, APP_TOOL_NAMES)
        self.assertEqual(len(tools), 14)

    def test_staleness_bands(self) -> None:
        self.assertEqual(staleness_band(0), "fresh")
        self.assertEqual(staleness_band(13), "fresh")
        self.assertEqual(staleness_band(14), "aging")
        self.assertEqual(staleness_band(45), "aging")
        self.assertEqual(staleness_band(46), "stale")
        self.assertIsNone(staleness_band(None))

    def test_ui_uri_helper(self) -> None:
        self.assertEqual(path_ui_uri("prep-card", versioned=False), "ui://ziksaka/prep-card")
        self.assertTrue(path_ui_uri("prep-card").startswith("ui://ziksaka/prep-card@"))


class TestLintFindingIds(unittest.IsolatedAsyncioTestCase):
    async def test_stale_finding_id(self) -> None:
        from src.apps.orchestrators.lint_apply import apply_lint_findings
        from unittest.mock import AsyncMock, patch

        # Without a vault, require_scope still works but lint will fail —
        # use a unit-level check on the result shape via stub.
        with patch(
            "src.apps.orchestrators.lint_apply.obsidian_tools"
        ) as mock_tools:
            intel = mock_tools._get_vault_intel.return_value
            intel.lint_vault = AsyncMock(
                return_value={
                    "content": [
                        {
                            "type": "text",
                            "text": '{"summary":{},"broken_wikilinks":[],'
                            '"alias_collisions":[],"orphan_entities":[],'
                            '"missing_required_frontmatter":[],'
                            '"missing_connections_section":[],'
                            '"invalid_event_type":[],"invalid_touchpoint_type":[]}',
                        }
                    ]
                }
            )
            result = await apply_lint_findings("work", ["bl-deadbeef"])
            self.assertIn("bl-deadbeef", result["stale"])
            self.assertEqual(result["applied"], [])


if __name__ == "__main__":
    unittest.main()
