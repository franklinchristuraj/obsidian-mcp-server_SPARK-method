"""Unit tests for GraphIndex (PRD_ziksaka-knowledge-graph, Phase 2)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

CLAROTY_MD = """---
type: entity
entity_type: customer
created: 2026-01-01
last_updated: 2026-05-02
agent_context: "Claroty is an OT security customer."
aliases: ["Claroty Inc", "Co Test"]
tags:
  - entity
  - customer
---

# Claroty

## Connections
- [[julien]] - champion
"""

JULIEN_MD = """---
type: entity
entity_type: person
created: 2026-01-01
last_updated: 2026-05-01
agent_context: "Julien is the Claroty champion."
aliases: []
tags:
  - entity
  - person
---

# Julien

Body text mentions [[process-mining]] in passing, not as a formal connection.

## Connections
- [[claroty]] - works at
"""

OT_SECURITY_MD = """---
type: entity
entity_type: concept
created: 2026-01-01
last_updated: 2026-01-01
agent_context: "OT security concept."
aliases: []
tags:
  - entity
  - concept
---

# OT Security
"""

PROCESS_MINING_MD = """---
type: entity
entity_type: concept
created: 2026-01-01
last_updated: 2026-01-01
agent_context: "Process mining concept."
aliases: []
tags:
  - entity
  - concept
---

# Process Mining
"""

EVENT_MD = """---
entity_type: event
event_type: discovery-call
event_date: 2026-05-01
aliases: []
customer: "[[claroty]]"
organizations:
  - "[[claroty]]"
  - "[[unknown-corp]]"
participants:
  - "[[julien]]"
concepts:
  - "[[ot-security]]"
last_updated: 2026-05-01
agent_context: "Discovery call."
---

# Claroty Discovery Call

## Connections
- [[claroty]] - customer
- [[julien]] - participant
"""

ORPHAN_MD = """---
type: entity
entity_type: customer
created: 2026-01-01
last_updated: 2026-01-01
agent_context: "Standalone customer with no connections."
aliases: ["Co Test"]
tags:
  - entity
  - customer
---

# Orphan Co
"""


class GraphFixtureTestCase(unittest.IsolatedAsyncioTestCase):
    """Hand-built temp vault: claroty (customer), julien (person), ot-security +
    process-mining (concepts), one event linking claroty/julien/ot-security (plus
    an unresolvable 'unknown-corp' org for the missing-entity check), and an
    unconnected orphan-co customer."""

    async def asyncSetUp(self) -> None:
        from src.vault_intelligence.graph import GraphIndex
        from src.vault_intelligence.tools import VaultIntelligenceTools

        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        ent = root / "work" / "entities"
        (ent / "customer").mkdir(parents=True)
        (ent / "person").mkdir(parents=True)
        (ent / "concept").mkdir(parents=True)
        (ent / "event").mkdir(parents=True)
        (ent / "customer" / "claroty.md").write_text(CLAROTY_MD, encoding="utf-8")
        (ent / "customer" / "orphan-co.md").write_text(ORPHAN_MD, encoding="utf-8")
        (ent / "person" / "julien.md").write_text(JULIEN_MD, encoding="utf-8")
        (ent / "concept" / "ot-security.md").write_text(OT_SECURITY_MD, encoding="utf-8")
        (ent / "concept" / "process-mining.md").write_text(
            PROCESS_MINING_MD, encoding="utf-8"
        )
        (ent / "event" / "2026-05-01-claroty-discovery-call.md").write_text(
            EVENT_MD, encoding="utf-8"
        )
        self.tools = VaultIntelligenceTools(str(root))
        notes = await self.tools._entity_notes("work")
        self.graph = GraphIndex(notes)

    async def asyncTearDown(self) -> None:
        self._tmp.cleanup()


class TestGraphEdgeExtraction(GraphFixtureTestCase):
    def test_engaged_with_from_event_customer_and_organizations(self) -> None:
        backlinks = self.graph.backlinks("claroty")
        engaged = [
            b
            for b in backlinks["backlinks"]
            if b["edge_type"] == "engaged_with" and "event" in b["path"]
        ]
        self.assertEqual(len(engaged), 1, "customer+organizations both pointing at claroty should dedupe to one engaged_with edge")
        self.assertEqual(engaged[0]["provenance"], "frontmatter")

    def test_attended_attendees_inverse_pair(self) -> None:
        event_backlinks = self.graph.backlinks("2026-05-01-claroty-discovery-call")
        attended = [b for b in event_backlinks["backlinks"] if b["edge_type"] == "attended"]
        self.assertTrue(any("julien" in b["path"] for b in attended))

        julien_backlinks = self.graph.backlinks("julien")
        attendees = [b for b in julien_backlinks["backlinks"] if b["edge_type"] == "attendees"]
        self.assertTrue(any("event" in b["path"] for b in attendees))

    def test_concepts_become_related_to(self) -> None:
        backlinks = self.graph.backlinks("ot-security")
        related = [b for b in backlinks["backlinks"] if b["edge_type"] == "related_to"]
        self.assertTrue(any("event" in b["path"] for b in related))
        self.assertEqual(related[0]["provenance"], "frontmatter")

    def test_connections_section_becomes_related_to_with_connections_provenance(self) -> None:
        backlinks = self.graph.backlinks("claroty")
        conn_edges = [
            b
            for b in backlinks["backlinks"]
            if b["edge_type"] == "related_to" and b["provenance"] == "connections"
        ]
        self.assertTrue(any("julien" in b["path"] for b in conn_edges))

    def test_body_only_link_becomes_mention(self) -> None:
        backlinks = self.graph.backlinks("process-mining")
        self.assertEqual(len(backlinks["backlinks"]), 1)
        self.assertEqual(backlinks["backlinks"][0]["edge_type"], "mention")
        self.assertEqual(backlinks["backlinks"][0]["provenance"], "body")

    def test_frontmatter_link_not_double_counted_as_mention(self) -> None:
        # ot-security is linked via concepts (frontmatter); it must not also
        # produce a weaker "mention" edge from the same source note.
        backlinks = self.graph.backlinks("ot-security")
        event_edges = [b for b in backlinks["backlinks"] if "event" in b["path"]]
        self.assertEqual(len(event_edges), 1)
        self.assertEqual(event_edges[0]["edge_type"], "related_to")

    def test_unresolvable_link_dropped_silently(self) -> None:
        for edge in self.graph.edges:
            self.assertNotIn("unknown-corp", edge.source)
            self.assertNotIn("unknown-corp", edge.target)


class TestGraphQueries(GraphFixtureTestCase):
    def test_neighbors_depth_1_both_directions(self) -> None:
        result = self.graph.neighbors("claroty", depth=1)
        self.assertTrue(result["resolved"])
        paths = {n["path"] for n in result["neighbors"]}
        self.assertIn("entities/person/julien.md", paths)
        self.assertIn("entities/event/2026-05-01-claroty-discovery-call.md", paths)

    def test_neighbors_rel_type_filter(self) -> None:
        result = self.graph.neighbors("claroty", depth=1, rel_type="engaged_with")
        paths = {n["path"] for n in result["neighbors"]}
        self.assertEqual(paths, {"entities/event/2026-05-01-claroty-discovery-call.md"})

    def test_neighbors_unresolved_name(self) -> None:
        result = self.graph.neighbors("totally-unknown-entity")
        self.assertFalse(result["resolved"])
        self.assertEqual(result["neighbors"], [])

    def test_shortest_path_two_hops_via_event(self) -> None:
        result = self.graph.shortest_path("julien", "ot-security")
        self.assertTrue(result["found"])
        self.assertEqual(result["hops"], 2)
        self.assertEqual(
            result["path"][-1]["to"], "entities/concept/ot-security.md"
        )

    def test_shortest_path_same_entity(self) -> None:
        result = self.graph.shortest_path("claroty", "claroty")
        self.assertTrue(result["found"])
        self.assertEqual(result["hops"], 0)

    def test_shortest_path_not_found_for_disconnected_orphan(self) -> None:
        result = self.graph.shortest_path("claroty", "orphan-co")
        self.assertTrue(result["resolved"])
        self.assertFalse(result["found"])

    def test_health_summary_orphan_and_counts(self) -> None:
        summary = self.graph.health_summary()
        self.assertEqual(summary["node_count"], 6)
        self.assertEqual(summary["orphan_count"], 1)
        self.assertEqual(summary["orphans"], ["entities/customer/orphan-co.md"])
        self.assertIn("engaged_with", summary["edge_type_counts"])
        self.assertIn("attended", summary["edge_type_counts"])
        self.assertIn("attendees", summary["edge_type_counts"])
        self.assertIn("related_to", summary["edge_type_counts"])
        self.assertIn("mention", summary["edge_type_counts"])


class TestGraphToolsIntegration(GraphFixtureTestCase):
    async def test_get_neighbors_tool(self) -> None:
        result = await self.tools.get_neighbors("claroty", scope="work", depth=1)
        data = json.loads(result["content"][0]["text"])
        self.assertTrue(data["resolved"])
        self.assertTrue(data["neighbors"])

    async def test_get_backlinks_tool(self) -> None:
        result = await self.tools.get_backlinks("claroty", scope="work")
        data = json.loads(result["content"][0]["text"])
        self.assertTrue(data["resolved"])
        self.assertTrue(data["backlinks"])

    async def test_find_path_tool(self) -> None:
        result = await self.tools.find_path("julien", "ot-security", scope="work")
        data = json.loads(result["content"][0]["text"])
        self.assertTrue(data["found"])

    async def test_find_path_no_match_raises(self) -> None:
        with self.assertRaises(ValueError):
            await self.tools.find_path("nope-does-not-exist", "claroty", scope="work")

    async def test_graph_health_tool_reports_missing_entity(self) -> None:
        result = await self.tools.graph_health(scope="work")
        data = json.loads(result["content"][0]["text"])
        self.assertIn("lint_summary", data)
        self.assertIn("graph", data)
        missing_names = {m["name"] for m in data["missing_entities"]}
        self.assertIn("unknown-corp", missing_names)
        self.assertEqual(data["graph"]["node_count"], 6)


RANDOM_NOTE_MD = """---
type: note
created: 2026-01-01
---

# Meeting scratch

Nothing to do with kumquat-zephyr-9000 entities, just a random note that
mentions the distinctive keyword kumquat-zephyr-9000 for search fallback.
"""


class TestBuildContext(GraphFixtureTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        root = Path(self._tmp.name)
        notes_dir = root / "work" / "notes"
        notes_dir.mkdir(parents=True, exist_ok=True)
        (notes_dir / "random-note.md").write_text(RANDOM_NOTE_MD, encoding="utf-8")

    async def test_resolves_entity_seed_and_expands_typed_first(self) -> None:
        result = await self.tools.build_context("claroty", scope="work", depth=1, token_budget=4000)
        data = json.loads(result["content"][0]["text"])
        self.assertEqual(data["seed"]["resolution"], "entity")
        self.assertEqual(data["seed"]["canonical_path"], "entities/customer/claroty.md")
        self.assertEqual(data["context_pack"][0]["tier"], "core")
        self.assertEqual(data["context_pack"][0]["path"], "entities/customer/claroty.md")
        # the engaged_with event (typed) must rank ahead of the plain related_to concept
        tiers_in_order = [item["tier"] for item in data["context_pack"]]
        self.assertLess(
            tiers_in_order.index("typed") if "typed" in tiers_in_order else 999,
            tiers_in_order.index("related") if "related" in tiers_in_order else 999,
        )
        self.assertEqual(data["source_manifest"][0], "entities/customer/claroty.md")

    async def test_respects_token_budget_and_marks_truncated(self) -> None:
        result = await self.tools.build_context("claroty", scope="work", depth=1, token_budget=1)
        data = json.loads(result["content"][0]["text"])
        # core is always included even if it alone exceeds the budget
        self.assertEqual(len(data["context_pack"]), 1)
        self.assertEqual(data["context_pack"][0]["tier"], "core")
        self.assertTrue(data["truncated"])
        self.assertLessEqual(len(data["source_manifest"]), 1)

    async def test_disambiguation_required_short_circuits(self) -> None:
        # claroty and orphan-co share the alias "Co Test" -> match_entities'
        # alias step finds two hits, forcing disambiguation before any graph work.
        result = await self.tools.build_context("Co Test", scope="work")
        data = json.loads(result["content"][0]["text"])
        self.assertTrue(data.get("disambiguation_required"), f"expected disambiguation, got: {data}")
        self.assertNotIn("seed", data)
        candidate_paths = {c["path"] for c in data["candidates"]}
        self.assertEqual(
            candidate_paths,
            {"entities/customer/claroty.md", "entities/customer/orphan-co.md"},
        )

    async def test_falls_back_to_search_for_non_entity_seed(self) -> None:
        result = await self.tools.build_context(
            "kumquat-zephyr-9000", scope="work", depth=1, token_budget=4000
        )
        data = json.loads(result["content"][0]["text"])
        self.assertEqual(data["seed"]["resolution"], "search")
        self.assertIn("random-note", data["seed"]["canonical_path"])
        self.assertEqual(data["context_pack"][0]["path"], data["seed"]["canonical_path"])

    async def test_no_match_at_all_raises(self) -> None:
        with self.assertRaises(ValueError):
            await self.tools.build_context(
                "zzz-absolutely-nothing-matches-this-qqq", scope="work"
            )


if __name__ == "__main__":
    unittest.main()
