"""Unit tests for vault intelligence parse layer and tools."""
from __future__ import annotations

import json
import os
import tempfile
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


class TestNormalizeLinkTarget(unittest.TestCase):
    def test_escaped_pipe_from_markdown_table_link(self) -> None:
        from src.vault_intelligence.parser import (
            WIKILINK_RE,
            normalize_link_target,
        )

        cell = r"| Action | [[entities/company/make-company\|Make]] |"
        target = WIKILINK_RE.search(cell).group(1)
        self.assertEqual(
            normalize_link_target(target), "entities/company/make-company"
        )

    def test_heading_and_block_references_are_stripped(self) -> None:
        from src.vault_intelligence.parser import normalize_link_target

        self.assertEqual(
            normalize_link_target("99_archive/poc.md#Open Questions"),
            "99_archive/poc.md",
        )
        self.assertEqual(normalize_link_target("poc.md#^abc123"), "poc.md")
        self.assertEqual(normalize_link_target("#Same Note Heading"), "")

    def test_windows_separators_and_relative_prefix_still_normalize(self) -> None:
        from src.vault_intelligence.parser import normalize_link_target

        self.assertEqual(
            normalize_link_target(r"./entities\customer\gojob.md"),
            "entities/customer/gojob.md",
        )


class TestFastFrontmatterAliases(unittest.TestCase):
    """Corpus scans parse frontmatter with a regex instead of yaml; both YAML
    list styles have to yield the same aliases or bare wikilinks silently stop
    resolving to block-style notes."""

    def _parse(self, body: str) -> object:
        from src.vault_intelligence.parser import parse_note

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "note.md"
            path.write_text(body, encoding="utf-8")
            return parse_note(path, "work", "note.md", include_sections=False)

    def test_block_style_alias_list(self) -> None:
        note = self._parse(
            "---\n"
            "aliases:\n"
            "  - POC Signal Log\n"
            "  - Signal Log\n"
            "type: resource\n"
            "---\n\nbody\n"
        )
        self.assertEqual(note.aliases, ["poc signal log", "signal log"])

    def test_inline_style_alias_list_unchanged(self) -> None:
        note = self._parse(
            "---\naliases: [Din, Den, Din Dedaqi]\ntype: entity\n---\n\nbody\n"
        )
        self.assertEqual(note.aliases, ["din", "den", "din dedaqi"])

    def test_empty_alias_list_yields_no_aliases(self) -> None:
        note = self._parse("---\naliases: []\ntype: entity\n---\n\nbody\n")
        self.assertEqual(note.aliases, [])


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


CLAROTY_MD = """---
type: entity
entity_type: customer
created: 2026-01-01
last_updated: 2026-05-02
agent_context: "Claroty is an OT security customer evaluating a POC."
poc_stage: discovery
aliases: ["Claroty Inc"]
tags:
  - entity
  - customer
---

# Claroty

## Connections
- [[entities/person/julien.md]] - champion

## Events
- [[2026-05-01-claroty-discovery-call]] — discovery-call, 2026-05-01

## Source History
- [2026-05-01] — Kickoff call [[2026-05-01-claroty-discovery-call]]
"""

EVENT_MD = """---
entity_type: event
event_type: discovery-call
event_date: 2026-05-01
aliases: []
customer: "[[claroty]]"
organizations:
  - "[[claroty]]"
participants:
  - "[[julien]]"
concepts: []
source_note: "[[11_work-meeting-notes/2026-05-01-claroty]]"
poc_stage: discovery
last_updated: 2026-05-01
source_count: 1
agent_context: "First discovery call with Claroty about an OT security POC."
---

# Claroty Discovery Call

> agent_context: First discovery call with Claroty.

## Connections
- [[claroty]] - customer
- [[julien]] - participant

## Outcome
- Agreed to a follow-up build session.
"""

JULIEN_MD = """---
type: entity
entity_type: person
created: 2026-01-01
last_updated: 2026-05-01
agent_context: "Julien is the Claroty champion."
aliases: ["Julien Martin"]
tags:
  - entity
  - person
---

# Julien

## Connections
- [[entities/customer/claroty.md]] - works at
"""


class TestEventEntitySupport(unittest.IsolatedAsyncioTestCase):
    """Self-contained tests for event-entity graph support using a temp vault."""

    async def asyncSetUp(self) -> None:
        from src.vault_intelligence.tools import VaultIntelligenceTools

        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        ent = root / "work" / "entities"
        (ent / "customer").mkdir(parents=True)
        (ent / "person").mkdir(parents=True)
        (ent / "event").mkdir(parents=True)
        (ent / "customer" / "claroty.md").write_text(CLAROTY_MD, encoding="utf-8")
        (ent / "person" / "julien.md").write_text(JULIEN_MD, encoding="utf-8")
        (ent / "event" / "2026-05-01-claroty-discovery-call.md").write_text(
            EVENT_MD, encoding="utf-8"
        )
        self.tools = VaultIntelligenceTools(str(root))

    async def asyncTearDown(self) -> None:
        self._tmp.cleanup()

    def test_required_fm_for_event_vs_default(self) -> None:
        from src.vault_intelligence.parser import REQUIRED_ENTITY_FM, required_fm_for

        self.assertEqual(required_fm_for("customer"), REQUIRED_ENTITY_FM)
        event_fm = required_fm_for("event")
        self.assertIn("event_type", event_fm)
        self.assertIn("event_date", event_fm)
        self.assertNotIn("created", event_fm)

    def test_parser_captures_frontmatter_links(self) -> None:
        from src.vault_intelligence.parser import parse_note

        note = parse_note(
            Path(self._tmp.name) / "work/entities/event/2026-05-01-claroty-discovery-call.md",
            "work",
            "entities/event/2026-05-01-claroty-discovery-call.md",
        )
        self.assertIn("claroty", note.frontmatter_links)
        self.assertIn("julien", note.frontmatter_links)
        self.assertIn("claroty", note.outlinks)

    async def test_event_bare_link_connection_resolves(self) -> None:
        result = await self.tools.resolve_entity(
            "2026-05-01-claroty-discovery-call", scope="work"
        )
        data = json.loads(result["content"][0]["text"])
        self.assertEqual(data["entity_type"], "event")
        self.assertEqual(data["key_frontmatter"].get("event_type"), "discovery-call")
        claroty_conn = [c for c in data["connections"] if c["display"] == "claroty"]
        self.assertTrue(claroty_conn, "bare [[claroty]] connection should resolve")
        self.assertTrue(claroty_conn[0]["agent_context_of_target"])

    async def test_customer_surfaces_events_and_backlink(self) -> None:
        result = await self.tools.resolve_entity("claroty", scope="work")
        data = json.loads(result["content"][0]["text"])
        event_paths = [e["path"] for e in data["events"]]
        self.assertTrue(
            any("2026-05-01-claroty-discovery-call" in p for p in event_paths),
            "## Events back-ref should surface the event",
        )
        backlink_paths = [b["path"] for b in data["backlinks"]]
        self.assertTrue(
            any("event/2026-05-01-claroty-discovery-call" in p for p in backlink_paths),
            "event frontmatter link should make it a backlink of the customer",
        )

    async def test_person_backlink_from_frontmatter(self) -> None:
        result = await self.tools.resolve_entity("julien", scope="work")
        data = json.loads(result["content"][0]["text"])
        backlink_paths = [b["path"] for b in data["backlinks"]]
        self.assertTrue(
            any("event/2026-05-01-claroty-discovery-call" in p for p in backlink_paths),
            "participant frontmatter link should backlink the event to the person",
        )

    async def test_query_frontmatter_event_type(self) -> None:
        result = await self.tools.query_frontmatter(
            {"entity_type": "event", "event_type": "discovery-call"},
            scope="work",
            folder="entities",
        )
        data = json.loads(result["content"][0]["text"])
        paths = [r["path"] for r in data["results"]]
        self.assertIn("entities/event/2026-05-01-claroty-discovery-call.md", paths)

    async def test_query_frontmatter_list_membership(self) -> None:
        # participants is a list of wikilinks; membership match should hit.
        result = await self.tools.query_frontmatter(
            {"entity_type": "event", "participants": "julien"},
            scope="work",
            folder="entities/event",
        )
        data = json.loads(result["content"][0]["text"])
        self.assertEqual(data["count"], 1)

    async def test_query_frontmatter_date_range(self) -> None:
        in_range = await self.tools.query_frontmatter(
            {"entity_type": "event", "event_date": {"gte": "2026-04-01", "lte": "2026-06-30"}},
            scope="work",
            folder="entities/event",
        )
        self.assertEqual(json.loads(in_range["content"][0]["text"])["count"], 1)
        out_range = await self.tools.query_frontmatter(
            {"entity_type": "event", "event_date": {"gte": "2026-06-01"}},
            scope="work",
            folder="entities/event",
        )
        self.assertEqual(json.loads(out_range["content"][0]["text"])["count"], 0)

    async def test_ranked_search_prefers_title_and_context(self) -> None:
        results = await self.tools.search_notes_ranked(
            "discovery", scope="work", limit=10
        )
        self.assertTrue(results)
        self.assertIn("event/2026-05-01-claroty-discovery-call", results[0]["path"])
        self.assertGreater(results[0]["score"], results[-1]["score"] - 0.01)

    async def test_resolve_entity_fuzzy_alias(self) -> None:
        # "Julien Marten" is a near-miss of the alias "Julien Martin".
        result = await self.tools.resolve_entity("Julien Marten", scope="work")
        data = json.loads(result["content"][0]["text"])
        self.assertIn("julien", data["canonical_path"])

    async def test_connection_carries_entity_type(self) -> None:
        result = await self.tools.resolve_entity(
            "2026-05-01-claroty-discovery-call", scope="work"
        )
        data = json.loads(result["content"][0]["text"])
        claroty = [c for c in data["connections"] if c["display"] == "claroty"][0]
        self.assertEqual(claroty["entity_type_of_target"], "customer")

    async def test_lint_event_schema_and_links(self) -> None:
        result = await self.tools.lint_vault(scope="work", folder="entities")
        data = json.loads(result["content"][0]["text"])
        missing = " ".join(data["missing_required_frontmatter"])
        self.assertNotIn("event/2026-05-01-claroty-discovery-call", missing)
        self.assertEqual(data["summary"]["invalid_event_type"], 0)
        broken = {b["link"] for b in data["broken_wikilinks"]}
        self.assertNotIn("claroty", broken)
        self.assertNotIn("julien", broken)

    async def test_timeline_includes_event_and_note_modifications(self) -> None:
        result = await self.tools.timeline("claroty", scope="work")
        data = json.loads(result["content"][0]["text"])
        self.assertEqual(data["canonical_path"], "entities/customer/claroty.md")
        types = {i["type"] for i in data["items"]}
        self.assertIn("event", types)
        event_items = [i for i in data["items"] if i["type"] == "event"]
        self.assertTrue(
            any("2026-05-01-claroty-discovery-call" in i["path"] for i in event_items)
        )
        # newest-first ordering
        dates = [i["date"] for i in data["items"]]
        self.assertEqual(dates, sorted(dates, reverse=True))

    async def test_timeline_start_end_range_filters(self) -> None:
        result = await self.tools.timeline(
            "claroty", scope="work", start="2026-06-01", end="2026-12-31"
        )
        data = json.loads(result["content"][0]["text"])
        self.assertEqual(data["items"], [])

    async def test_last_touch_returns_newest_item(self) -> None:
        timeline_result = await self.tools.timeline("claroty", scope="work")
        timeline_data = json.loads(timeline_result["content"][0]["text"])

        result = await self.tools.last_touch("claroty", scope="work")
        data = json.loads(result["content"][0]["text"])
        self.assertEqual(data["canonical_path"], "entities/customer/claroty.md")
        self.assertEqual(data["last_touch"]["date"], timeline_data["items"][0]["date"])
        self.assertEqual(data["last_touch"]["type"], "event")
        self.assertFalse(data["fallback_to_note_modified"])

    async def test_last_touch_prefers_event_over_newer_note_modified(self) -> None:
        """Regression for the Reception PRD 1 §6 bug: a linked note's
        `last_updated` (edited for reasons unrelated to this entity) must
        not outrank a real event just because its date is more recent.
        """
        root = Path(self._tmp.name)
        julien_path = root / "work" / "entities" / "person" / "julien.md"
        # Julien's card gets touched a month after the actual Claroty
        # interaction — e.g. an unrelated alias cleanup — which must not
        # make last_touch claim Claroty was "touched" on 2026-06-15.
        julien_path.write_text(JULIEN_MD.replace("last_updated: 2026-05-01", "last_updated: 2026-06-15"), encoding="utf-8")
        self.tools.corpus.clear_cache()

        timeline_result = await self.tools.timeline("claroty", scope="work")
        timeline_data = json.loads(timeline_result["content"][0]["text"])
        # Confirm the fixture actually exercises the bug: the newest item
        # overall is now the note_modified one, not the event.
        self.assertEqual(timeline_data["items"][0]["type"], "note_modified")
        self.assertEqual(timeline_data["items"][0]["date"], "2026-06-15")

        result = await self.tools.last_touch("claroty", scope="work")
        data = json.loads(result["content"][0]["text"])
        self.assertEqual(data["last_touch"]["type"], "event")
        self.assertEqual(data["last_touch"]["date"], "2026-05-01")
        self.assertFalse(data["fallback_to_note_modified"])

    async def test_last_touch_falls_back_to_note_modified_when_flagged(self) -> None:
        """When an entity has no event or dated mention at all, last_touch
        may fall back to note_modified — but must say so explicitly."""
        root = Path(self._tmp.name)
        # Strip Claroty's event link and Source History so only
        # note_modified items remain in its timeline.
        stripped = CLAROTY_MD.replace(
            '## Events\n- [[2026-05-01-claroty-discovery-call]] — discovery-call, 2026-05-01\n\n',
            "",
        ).replace(
            "## Source History\n- [2026-05-01] — Kickoff call [[2026-05-01-claroty-discovery-call]]\n",
            "",
        )
        (root / "work" / "entities" / "customer" / "claroty.md").write_text(stripped, encoding="utf-8")
        self.tools.corpus.clear_cache()

        result = await self.tools.last_touch("claroty", scope="work")
        data = json.loads(result["content"][0]["text"])
        self.assertEqual(data["last_touch"]["type"], "note_modified")
        self.assertTrue(data["fallback_to_note_modified"])

    async def test_get_dossier_since_adds_changes_since_without_altering_default(self) -> None:
        baseline = await self.tools.get_dossier("claroty", scope="work")
        baseline_data = json.loads(baseline["content"][0]["text"])
        self.assertNotIn("changes_since", baseline_data)

        result = await self.tools.get_dossier("claroty", scope="work", since="2026-05-01")
        data = json.loads(result["content"][0]["text"])
        self.assertEqual(data["since"], "2026-05-01")
        self.assertIn("changes_since", data)
        self.assertTrue(
            any(
                "2026-05-01-claroty-discovery-call" in e["path"]
                for e in data["changes_since"]["events"]
            )
        )
        # everything else must be identical to the no-since call
        for key in ("entity", "connections", "backlinks", "events", "recent_mentions"):
            self.assertEqual(data[key], baseline_data[key])

    async def test_get_dossier_since_future_date_empties_changes(self) -> None:
        result = await self.tools.get_dossier("claroty", scope="work", since="2099-01-01")
        data = json.loads(result["content"][0]["text"])
        self.assertEqual(data["changes_since"]["events"], [])
        self.assertEqual(data["changes_since"]["mentions"], [])


CARLOS_QUIROS_MD = """---
type: entity
entity_type: person
created: 2026-01-01
agent_context: "Carlos Quiros, VE org."
tags:
  - entity
  - person
---

# Carlos Quiros
"""

STALE_LINK_MD = """---
type: entity
entity_type: customer
created: 2026-01-01
agent_context: "Some note with a stale link."
tags:
  - entity
  - customer
---

# Some Note

## Connections
- [[entities/internal-stakeholder/carlos-quiros]] - contact
"""

ACME_CUSTOMER_MD = """---
type: entity
entity_type: customer
created: 2026-01-01
agent_context: "Acme the customer."
tags:
  - entity
  - customer
---

# Acme Customer
"""

ACME_COMPANY_MD = """---
type: entity
entity_type: company
created: 2026-01-01
agent_context: "Acme the company."
tags:
  - entity
  - company
---

# Acme Company
"""

AMBIGUOUS_LINK_MD = """---
type: entity
entity_type: customer
created: 2026-01-01
agent_context: "Mentions the ambiguous acme stem."
tags:
  - entity
  - customer
---

# Mentions Acme

## Connections
- [[acme]] - related
"""


class TestLintVaultFix(unittest.IsolatedAsyncioTestCase):
    """lint_vault(fix=True): rewrite unambiguous stale links, leave ambiguous ones alone."""

    async def asyncSetUp(self) -> None:
        from src.vault_intelligence.tools import VaultIntelligenceTools

        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        ent = root / "work" / "entities"
        (ent / "person").mkdir(parents=True)
        (ent / "customer").mkdir(parents=True)
        (ent / "company").mkdir(parents=True)
        (ent / "person" / "carlos-quiros.md").write_text(CARLOS_QUIROS_MD, encoding="utf-8")
        (ent / "customer" / "some-note.md").write_text(STALE_LINK_MD, encoding="utf-8")
        (ent / "customer" / "acme.md").write_text(ACME_CUSTOMER_MD, encoding="utf-8")
        (ent / "company" / "acme.md").write_text(ACME_COMPANY_MD, encoding="utf-8")
        (ent / "customer" / "mentions-acme.md").write_text(AMBIGUOUS_LINK_MD, encoding="utf-8")
        self.root = root
        self.tools = VaultIntelligenceTools(str(root))

    async def asyncTearDown(self) -> None:
        self._tmp.cleanup()

    async def test_baseline_reports_both_broken_links(self) -> None:
        result = await self.tools.lint_vault(scope="work", folder="entities")
        data = json.loads(result["content"][0]["text"])
        broken = {b["link"] for b in data["broken_wikilinks"]}
        self.assertIn("entities/internal-stakeholder/carlos-quiros", broken)
        self.assertIn("acme", broken)

    async def test_fix_rewrites_stale_full_path_link(self) -> None:
        result = await self.tools.lint_vault(scope="work", folder="entities", fix=True)
        data = json.loads(result["content"][0]["text"])
        fix_report = data["fix_report"]

        rewritten_links = {r["link"] for r in fix_report["rewritten"]}
        self.assertIn("entities/internal-stakeholder/carlos-quiros", rewritten_links)

        on_disk = (self.root / "work/entities/customer/some-note.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("[[carlos-quiros]]", on_disk)
        self.assertNotIn("entities/internal-stakeholder/carlos-quiros", on_disk)

    async def test_fix_leaves_ambiguous_link_unrewritten(self) -> None:
        result = await self.tools.lint_vault(scope="work", folder="entities", fix=True)
        data = json.loads(result["content"][0]["text"])
        fix_report = data["fix_report"]

        ambiguous_links = {r["link"] for r in fix_report["still_ambiguous"]}
        self.assertIn("acme", ambiguous_links)

        on_disk = (self.root / "work/entities/customer/mentions-acme.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("[[acme]]", on_disk)

        # Post-fix rescan: the stale-path link is gone, the ambiguous one remains.
        broken = {b["link"] for b in data["broken_wikilinks"]}
        self.assertNotIn("entities/internal-stakeholder/carlos-quiros", broken)
        self.assertIn("acme", broken)


class _FakeObsidianClient:
    """Filesystem-backed stand-in for ObsidianClient (REST) in create_event tests."""

    def __init__(self, vault_path: str):
        self.vault_path = vault_path

    def _full(self, p: str) -> Path:
        return Path(self.vault_path) / p

    async def note_exists(self, path: str) -> bool:
        return self._full(path).is_file()

    async def read_note(self, path: str) -> str:
        return self._full(path).read_text(encoding="utf-8")

    async def update_note(self, path: str, content: str) -> bool:
        self._full(path).write_text(content, encoding="utf-8")
        return True

    async def create_note(self, path: str, content: str, create_folders: bool = True) -> bool:
        full = self._full(path)
        if create_folders:
            full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
        return True


class TestUpsertEventsSection(unittest.TestCase):
    def test_insert_idempotent_and_sorted(self) -> None:
        from src.tools.obsidian_tools import _upsert_events_section

        card = (
            "---\nentity_type: customer\nagent_context: x\n---\n\n"
            "# Claroty\n\n## Connections\n- [[julien]]\n\n"
            "## Source History\n- [2026-01-01] — note\n"
        )
        out, changed = _upsert_events_section(
            card, "2026-06-01-claroty-discovery-call", "discovery-call", "2026-06-01"
        )
        self.assertTrue(changed)
        self.assertLess(out.index("## Events"), out.index("## Source History"))
        self.assertTrue(out.startswith("---\nentity_type: customer\nagent_context: x\n---"))

        out2, changed2 = _upsert_events_section(
            out, "2026-06-01-claroty-discovery-call", "discovery-call", "2026-06-01"
        )
        self.assertFalse(changed2)

        out3, _ = _upsert_events_section(out, "2026-07-01-claroty-demo", "demo", "2026-07-01")
        events_block = out3.split("## Events", 1)[1]
        first_line = events_block.strip().splitlines()[0]
        self.assertIn("2026-07-01", first_line)


class TestCreateEventTool(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        from src.tools.obsidian_tools import ObsidianTools

        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        ent = root / "work" / "entities"
        (ent / "customer").mkdir(parents=True)
        (ent / "person").mkdir(parents=True)
        (ent / "customer" / "claroty.md").write_text(CLAROTY_MD, encoding="utf-8")
        (ent / "person" / "julien.md").write_text(JULIEN_MD, encoding="utf-8")

        self.tools = ObsidianTools()
        self.tools.client = _FakeObsidianClient(str(root))
        self.tools._vault_intel = None
        self.root = root

    async def asyncTearDown(self) -> None:
        self._tmp.cleanup()

    async def test_create_event_writes_card_and_backrefs(self) -> None:
        result = await self.tools.create_event(
            event_type="discovery-call",
            event_date="2026-06-01",
            customer="Claroty",
            participants=["Julien"],
            agent_context="Discovery call with Claroty.",
            scope="work",
        )
        meta = result["metadata"]
        self.assertEqual(meta["path"], "entities/event/2026-06-01-claroty-discovery-call.md")

        event_file = self.root / "work" / meta["path"]
        self.assertTrue(event_file.is_file())
        body = event_file.read_text(encoding="utf-8")
        self.assertIn("entity_type: event", body)
        self.assertIn('customer: "[[claroty]]"', body)

        # Back-ref written into the customer card before ## Source History.
        claroty = (self.root / "work/entities/customer/claroty.md").read_text(encoding="utf-8")
        self.assertIn("## Events", claroty)
        self.assertIn("[[2026-06-01-claroty-discovery-call]]", claroty)

        statuses = {r["entity"]: r["status"] for r in meta["backref_results"]}
        self.assertEqual(
            statuses.get("entities/customer/claroty.md"), "updated"
        )
        self.assertEqual(statuses.get("entities/person/julien.md"), "updated")

    async def test_invalid_event_type_rejected(self) -> None:
        with self.assertRaises(ValueError):
            await self.tools.create_event(event_type="lunch", scope="work")

    async def test_filename_collision_suffix(self) -> None:
        for _ in range(2):
            await self.tools.create_event(
                event_type="discovery-call",
                event_date="2026-06-01",
                customer="Claroty",
                scope="work",
                update_backrefs=False,
            )
        events_dir = self.root / "work/entities/event"
        names = sorted(p.name for p in events_dir.glob("*.md"))
        self.assertIn("2026-06-01-claroty-discovery-call.md", names)
        self.assertIn("2026-06-01-claroty-discovery-call-2.md", names)

    async def test_create_event_parent_engagement_and_touchpoint(self) -> None:
        eng_dir = self.root / "work/12_engagements"
        eng_dir.mkdir(parents=True)
        parent = eng_dir / "2026-06-01_claroty-build-with-me.md"
        parent.write_text(
            "---\ntype: engagement\nengagement_type: build-with-me\n"
            "customer: \"[[claroty]]\"\nstatus: scheduled\n"
            "agent_context: Claroty BWM\ntags: [engagement]\n---\n\n"
            "# Claroty BWM\n\n## Interactions\n\n-\n\n## Next Actions\n\n- [ ] x\n",
            encoding="utf-8",
        )

        result = await self.tools.create_event(
            event_type="build-with-me",
            event_date="2026-06-01",
            customer="Claroty",
            parent_engagement="2026-06-01_claroty-build-with-me",
            touchpoint_type="kickoff-workshop",
            channel="workshop",
            adoption_stage="trial-start",
            scope="work",
        )
        meta = result["metadata"]
        self.assertEqual(
            meta["path"],
            "entities/event/2026-06-01-claroty-kickoff-workshop.md",
        )
        self.assertEqual(meta["touchpoint_type"], "kickoff-workshop")
        self.assertEqual(meta["parent_engagement"], "2026-06-01_claroty-build-with-me")

        event_body = (self.root / "work" / meta["path"]).read_text(encoding="utf-8")
        self.assertIn("touchpoint_type: kickoff-workshop", event_body)
        self.assertIn('parent_engagement: "[[2026-06-01_claroty-build-with-me]]"', event_body)

        parent_body = parent.read_text(encoding="utf-8")
        self.assertIn("[[2026-06-01-claroty-kickoff-workshop]]", parent_body)
        self.assertIn("## Interactions", parent_body)

    async def test_invalid_touchpoint_type_rejected(self) -> None:
        with self.assertRaises(ValueError):
            await self.tools.create_event(
                event_type="build-with-me",
                touchpoint_type="coffee-chat",
                scope="work",
                update_backrefs=False,
            )

    async def test_technical_deep_dive_event_type_accepted(self) -> None:
        result = await self.tools.create_event(
            event_type="technical-deep-dive",
            event_date="2026-06-02",
            customer="Claroty",
            requested_by="Julien",
            technical_domains=["mcp", "sap-onprem"],
            scope="work",
            update_backrefs=False,
        )
        body = (self.root / "work" / result["metadata"]["path"]).read_text(
            encoding="utf-8"
        )
        self.assertIn("event_type: technical-deep-dive", body)
        self.assertIn("mcp", body)
        self.assertIn('requested_by: "[[julien]]"', body)


class TestCreateEngagementTool(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        from src.tools.obsidian_tools import ObsidianTools

        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        ent = root / "work" / "entities"
        (ent / "customer").mkdir(parents=True)
        (ent / "customer" / "claroty.md").write_text(CLAROTY_MD, encoding="utf-8")
        (root / "work" / "12_engagements").mkdir(parents=True)
        (root / "work" / "index.md").write_text("# Index\n\n", encoding="utf-8")
        (root / "work" / "log.md").write_text("# Log\n\n", encoding="utf-8")

        self.tools = ObsidianTools()
        self.tools.client = _FakeObsidianClient(str(root))
        self.tools._vault_intel = None
        self.root = root

    async def asyncTearDown(self) -> None:
        self._tmp.cleanup()

    async def test_create_bwm_engagement(self) -> None:
        result = await self.tools.create_engagement(
            engagement_type="build-with-me",
            date="2026-07-01",
            customer="Claroty",
            trial_start="2026-07-01",
            trial_end="2026-07-31",
            next_touch="2026-07-08",
            next_touch_type="mid-trial-review",
            champion="Julien",
            scope="work",
        )
        meta = result["metadata"]
        self.assertEqual(
            meta["path"], "12_engagements/2026-07-01_claroty-build-with-me.md"
        )
        body = (self.root / "work" / meta["path"]).read_text(encoding="utf-8")
        self.assertIn("engagement_type: build-with-me", body)
        self.assertIn("trial_start:", body)
        self.assertIn("2026-07-01", body)
        self.assertIn("adoption_health: on-track", body)
        self.assertIn("## Interactions", body)
        self.assertIn("## High-signal debrief", body)

        index = (self.root / "work/index.md").read_text(encoding="utf-8")
        self.assertIn("2026-07-01_claroty-build-with-me", index)

    async def test_create_technical_deep_dive_requires_owning_ve(self) -> None:
        with self.assertRaises(ValueError):
            await self.tools.create_engagement(
                engagement_type="technical-deep-dive",
                customer="Claroty",
                scope="work",
                update_index=False,
            )

        result = await self.tools.create_engagement(
            engagement_type="technical-deep-dive",
            date="2026-07-02",
            customer="Claroty",
            owning_ve="anna-stafeeva",
            technical_domains=["mcp"],
            sales_stage="poc",
            scope="work",
            update_index=False,
        )
        body = (self.root / "work" / result["metadata"]["path"]).read_text(
            encoding="utf-8"
        )
        self.assertIn("engagement_type: technical-deep-dive", body)
        self.assertIn("mcp", body)

    async def test_invalid_engagement_type_rejected(self) -> None:
        with self.assertRaises(ValueError):
            await self.tools.create_engagement(
                engagement_type="lunch-and-learn",
                customer="Claroty",
                scope="work",
                update_index=False,
            )

    async def test_path_traversal_slug_rejected(self) -> None:
        with self.assertRaises(ValueError):
            await self.tools.create_engagement(
                engagement_type="demo",
                customer="Claroty",
                slug="../evil",
                scope="work",
                update_index=False,
            )


class TestUpsertInteractionsSection(unittest.TestCase):
    def test_insert_idempotent(self) -> None:
        from src.tools.obsidian_tools import _upsert_interactions_section

        note = (
            "---\ntype: engagement\n---\n\n# BWM\n\n## Interactions\n\n-\n\n"
            "## Next Actions\n\n- [ ] x\n"
        )
        out, changed = _upsert_interactions_section(
            note,
            "2026-07-01-claroty-kickoff-workshop",
            "build-with-me",
            "2026-07-01",
            touchpoint_type="kickoff-workshop",
        )
        self.assertTrue(changed)
        self.assertIn("[[2026-07-01-claroty-kickoff-workshop]]", out)
        out2, changed2 = _upsert_interactions_section(
            out,
            "2026-07-01-claroty-kickoff-workshop",
            "build-with-me",
            "2026-07-01",
            touchpoint_type="kickoff-workshop",
        )
        self.assertFalse(changed2)


class TestWriteTimeValidation(unittest.IsolatedAsyncioTestCase):
    """Alias-collision blocking + unresolved-link warnings on create_note/update_note."""

    async def asyncSetUp(self) -> None:
        from src.tools.obsidian_tools import ObsidianTools

        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        ent = root / "work" / "entities"
        (ent / "customer").mkdir(parents=True)
        (ent / "person").mkdir(parents=True)
        (ent / "customer" / "claroty.md").write_text(CLAROTY_MD, encoding="utf-8")
        (ent / "person" / "julien.md").write_text(JULIEN_MD, encoding="utf-8")

        self.tools = ObsidianTools()
        self.tools.client = _FakeObsidianClient(str(root))
        self.tools._vault_intel = None
        self.root = root

    async def asyncTearDown(self) -> None:
        self._tmp.cleanup()

    async def test_new_alias_colliding_with_another_entity_blocks_update(self) -> None:
        new_content = JULIEN_MD.replace(
            'aliases: ["Julien Martin"]', 'aliases: ["Julien Martin", "Claroty Inc"]'
        )
        with self.assertRaises(ValueError) as ctx:
            await self.tools.update_note(
                path="entities/person/julien.md", content=new_content, scope="work"
            )
        self.assertIn("alias collision", str(ctx.exception))

        # The write must not have happened.
        on_disk = (self.root / "work/entities/person/julien.md").read_text(encoding="utf-8")
        self.assertNotIn("Claroty Inc", on_disk)

    async def test_unchanged_alias_does_not_block_update(self) -> None:
        new_content = JULIEN_MD.replace(
            "Julien is the Claroty champion.",
            "Julien is the Claroty champion (updated).",
        )
        result = await self.tools.update_note(
            path="entities/person/julien.md", content=new_content, scope="work"
        )
        self.assertIn("Successfully updated", result["content"][0]["text"])

    async def test_unresolved_outgoing_link_surfaces_warning(self) -> None:
        content = (
            "---\n"
            "type: entity\n"
            "entity_type: person\n"
            "created: 2026-01-01\n"
            'agent_context: "A new contact."\n'
            "tags:\n  - entity\n  - person\n"
            "aliases: []\n"
            "---\n\n"
            "# New Contact\n\n"
            "## Connections\n"
            "- [[nobody-known]] - related\n"
        )
        result = await self.tools.create_note(
            path="entities/person/new-contact.md",
            content=content,
            scope="work",
            use_template=False,
        )
        warnings = result["metadata"]["validation_warnings"]
        joined = " ".join(warnings)
        self.assertIn("unresolved outgoing wikilinks", joined)
        self.assertIn("nobody-known", joined)

    async def test_resolvable_outgoing_link_has_no_warning(self) -> None:
        content = (
            "---\n"
            "type: entity\n"
            "entity_type: person\n"
            "created: 2026-01-01\n"
            'agent_context: "Another contact."\n'
            "tags:\n  - entity\n  - person\n"
            "aliases: []\n"
            "---\n\n"
            "# Another Contact\n\n"
            "## Connections\n"
            "- [[claroty]] - customer\n"
        )
        result = await self.tools.create_note(
            path="entities/person/another-contact.md",
            content=content,
            scope="work",
            use_template=False,
        )
        warnings = result["metadata"]["validation_warnings"]
        joined = " ".join(warnings)
        self.assertNotIn("unresolved outgoing wikilinks", joined)


class TestToolRegistry(unittest.TestCase):
    def test_vault_intel_tools_registered(self) -> None:
        from src.tools.obsidian_tools import OBSIDIAN_TOOL_DISPATCH, obsidian_tools

        expected = {
            "resolve_entity",
            "query_frontmatter",
            "get_dossier",
            "lint_vault",
            "get_backlinks",
            "get_neighbors",
            "find_path",
            "graph_health",
            "timeline",
            "last_touch",
            "build_context",
        }
        for name in expected:
            self.assertIn(name, OBSIDIAN_TOOL_DISPATCH)
        listed = {t.name for t in obsidian_tools.get_tools()}
        self.assertTrue(expected <= listed)


if __name__ == "__main__":
    unittest.main()
