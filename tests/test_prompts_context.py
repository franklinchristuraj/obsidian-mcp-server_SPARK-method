"""Agent-facing context (guide, prompts, initialize instructions) stays in step with the vault."""
from __future__ import annotations

import unittest

from src.mcp_server import _PROMPTS_GET_DESCRIPTIONS, MCPProtocolHandler
from src.prompts.obsidian_prompts import obsidian_prompts
from src.vault_intelligence.parser import ENTITY_TYPES


class TestAgentGuide(unittest.IsolatedAsyncioTestCase):
    async def test_guide_covers_fde_hub(self) -> None:
        guide = await obsidian_prompts.get_prompt_content("vault_mcp_agent_guide")
        self.assertIn("03_areas/fde/_index.md", guide)
        self.assertIn("not a workspace", guide)
        self.assertIn("fde-evidence-log.md", guide)
        self.assertIn("fde_workflow", guide)

    async def test_guide_uses_canonical_meeting_folder(self) -> None:
        guide = await obsidian_prompts.get_prompt_content("vault_mcp_agent_guide")
        self.assertIn("`11_meeting-notes/` (canonical", guide)

    async def test_guide_lists_spectrum_rules(self) -> None:
        guide = await obsidian_prompts.get_prompt_content("vault_mcp_agent_guide")
        self.assertIn("topic-catalog.md", guide)
        self.assertIn("pain-point", guide)


class TestFdeWorkflowPrompt(unittest.IsolatedAsyncioTestCase):
    def test_listed(self) -> None:
        names = {p.name for p in obsidian_prompts.get_prompts()}
        self.assertIn("fde_workflow", names)

    async def test_renders_with_customer(self) -> None:
        body = await obsidian_prompts.get_prompt_content(
            "fde_workflow", {"customer": "Acme"}
        )
        self.assertIn('customer="Acme"', body)
        self.assertIn('scope="work"', body)
        self.assertIn("hypotheses", body)


class TestPromptDescriptions(unittest.TestCase):
    def test_every_prompt_has_get_description(self) -> None:
        names = {p.name for p in obsidian_prompts.get_prompts()}
        self.assertEqual(names - set(_PROMPTS_GET_DESCRIPTIONS), set())

    def test_instructions_mention_fde(self) -> None:
        handler = MCPProtocolHandler()
        self.assertIn("fde_workflow", handler.instructions)
        self.assertIn("scope=work", handler.instructions)


class TestEntityTypes(unittest.TestCase):
    def test_work_ontology_types_known(self) -> None:
        self.assertIn("pain-point", ENTITY_TYPES)
        self.assertIn("framework", ENTITY_TYPES)


if __name__ == "__main__":
    unittest.main()
