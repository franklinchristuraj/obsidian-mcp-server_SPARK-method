"""Registry contract: every advertised MCP tool name must dispatch to a real handler."""
import unittest

from src.mcp_server import mcp_handler
from src.tools.obsidian_tools import (
    OBSIDIAN_TOOL_DISPATCH,
    OBSIDIAN_ROUTED_TOOL_NAMES,
    obsidian_tools,
)


class TestToolRegistryContract(unittest.TestCase):
    def test_dispatch_keys_match_routed_set(self) -> None:
        self.assertEqual(
            set(OBSIDIAN_TOOL_DISPATCH.keys()),
            OBSIDIAN_ROUTED_TOOL_NAMES,
        )

    def test_get_tools_matches_dispatch(self) -> None:
        listed = {t.name for t in obsidian_tools.get_tools()}
        self.assertEqual(
            listed,
            OBSIDIAN_ROUTED_TOOL_NAMES,
            msg="get_tools() names must equal OBSIDIAN_TOOL_DISPATCH keys",
        )

    def test_each_handler_is_callable(self) -> None:
        for tool_name, method_name in OBSIDIAN_TOOL_DISPATCH.items():
            target = getattr(obsidian_tools, method_name, None)
            self.assertTrue(
                callable(target),
                msg=f"Tool {tool_name!r} maps to missing/non-callable {method_name!r}",
            )

    def test_mcp_handler_obsidian_subset(self) -> None:
        handler_names = {t.name for t in mcp_handler.tools}
        obs_names = {t.name for t in obsidian_tools.get_tools()}
        self.assertIn("ping", handler_names)
        self.assertTrue(obs_names <= handler_names)
        self.assertEqual(handler_names - obs_names, {"ping"})
        self.assertEqual(len(handler_names), len(set(handler_names)))


if __name__ == "__main__":
    unittest.main()
