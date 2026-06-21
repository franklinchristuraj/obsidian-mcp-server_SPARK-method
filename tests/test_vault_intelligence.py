"""Unit tests for vault intelligence parse layer and tools."""
from __future__ import annotations

import json
import os
import time
import unittest
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

VAULT = os.getenv(
    "OBSIDIAN_VAULT_PATH",
    "/home/franklinchris/obsidian/config/franklin-vault",
)
GOJOB = Path(VAULT) / "work/entities/customer/gojob.md"


class TestParseNote(unittest.TestCase):
    def test_parse_gojob_structure(self) -> None:
        from src.vault_intelligence.parser import (
            CONNECTIONS_HEADING,
            SOURCE_HISTORY_HEADING,
            extract_section_links,
            extract_source_history_entries,
            parse_note,
        )

        self.assertTrue(GOJOB.is_file(), f"fixture missing: {GOJOB}")
        note = parse_note(GOJOB, "work", "entities/customer/gojob.md")

        self.assertEqual(note.path, "entities/customer/gojob.md")
        self.assertEqual(note.frontmatter.get("entity_type"), "customer")
        self.assertIn("gojob", note.agent_context.lower())
        self.assertIn("gojob", [a.lower() for a in (note.frontmatter.get("aliases") or [])])
        self.assertIn(CONNECTIONS_HEADING, note.sections)
        self.assertIn(SOURCE_HISTORY_HEADING, note.sections)

        links = extract_section_links(note)
        self.assertTrue(any("julien" in l for l in links))

        history = extract_source_history_entries(note)
        self.assertGreaterEqual(len(history), 1)
        self.assertRegex(history[0]["date"], r"^\d{4}-\d{2}-\d{2}$")


class TestVaultIntelligenceTools(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        from src.vault_intelligence.tools import VaultIntelligenceTools

        self.tools = VaultIntelligenceTools(VAULT)

    async def test_resolve_entity_gojob(self) -> None:
        result = await self.tools.resolve_entity("gojob", scope="work")
        data = json.loads(result["content"][0]["text"])
        self.assertEqual(data["canonical_path"], "entities/customer/gojob.md")
        self.assertEqual(data["entity_type"], "customer")
        self.assertTrue(data["connections"])

    async def test_resolve_entity_alias_gojab(self) -> None:
        result = await self.tools.resolve_entity("Gojab", scope="work")
        data = json.loads(result["content"][0]["text"])
        self.assertEqual(data["canonical_path"], "entities/customer/gojob.md")

    async def test_resolve_entity_fuzzy_gojo(self) -> None:
        result = await self.tools.resolve_entity("gojo", scope="work")
        data = json.loads(result["content"][0]["text"])
        self.assertEqual(data["canonical_path"], "entities/customer/gojob.md")

    async def test_resolve_entity_julien(self) -> None:
        result = await self.tools.resolve_entity("Julien", scope="work")
        data = json.loads(result["content"][0]["text"])
        self.assertIn("julien", data["canonical_path"])

    async def test_query_frontmatter_discovery(self) -> None:
        result = await self.tools.query_frontmatter(
            {"entity_type": "customer", "poc_stage": "discovery"},
            scope="work",
            folder="entities",
        )
        data = json.loads(result["content"][0]["text"])
        paths = [r["path"] for r in data["results"]]
        self.assertIn("entities/customer/gojob.md", paths)

    async def test_get_dossier_gojob(self) -> None:
        result = await self.tools.get_dossier("gojob", scope="work")
        data = json.loads(result["content"][0]["text"])
        self.assertEqual(data["entity"]["canonical_path"], "entities/customer/gojob.md")
        self.assertIn("agent_context", data["entity"])
        self.assertIn("open_questions", data)

    async def test_corpus_cold_parse_under_one_second(self) -> None:
        self.tools.corpus.clear_cache()
        start = time.perf_counter()
        notes = self.tools.corpus.load_scope(["work"], include_sections=False)
        elapsed = time.perf_counter() - start
        self.assertGreater(len(notes), 200)
        self.assertLess(elapsed, 1.0, f"cold parse took {elapsed:.2f}s")


class TestToolRegistry(unittest.TestCase):
    def test_vault_intel_tools_registered(self) -> None:
        from src.tools.obsidian_tools import OBSIDIAN_TOOL_DISPATCH, obsidian_tools

        for name in ("resolve_entity", "query_frontmatter", "get_dossier", "lint_vault"):
            self.assertIn(name, OBSIDIAN_TOOL_DISPATCH)
        listed = {t.name for t in obsidian_tools.get_tools()}
        self.assertTrue({"resolve_entity", "query_frontmatter", "get_dossier", "lint_vault"} <= listed)


if __name__ == "__main__":
    unittest.main()
