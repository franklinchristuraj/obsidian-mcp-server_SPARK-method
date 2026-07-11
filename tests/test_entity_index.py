"""Unit tests for the shared name/alias/path resolution primitives."""
from __future__ import annotations

import unittest

from src.vault_intelligence.entity_index import EntityIndex, build_name_index
from src.vault_intelligence.parser import ParsedNote


def _note(path: str, aliases=None) -> ParsedNote:
    return ParsedNote(
        path=path,
        scope="work",
        frontmatter={},
        aliases=[a.lower() for a in (aliases or [])],
        body="",
        sections={},
        outlinks=[],
        agent_context="",
    )


class TestBuildNameIndex(unittest.TestCase):
    def test_unique_stems_and_aliases_indexed(self) -> None:
        notes = [_note("entities/customer/claroty.md", aliases=["Claroty Inc"])]
        idx, ambiguous = build_name_index(notes)
        self.assertIs(idx["claroty"], notes[0])
        self.assertIs(idx["claroty inc"], notes[0])
        self.assertEqual(ambiguous, set())

    def test_colliding_stem_is_dropped_and_marked_ambiguous(self) -> None:
        notes = [
            _note("entities/customer/acme.md"),
            _note("entities/company/acme.md"),
        ]
        idx, ambiguous = build_name_index(notes)
        self.assertNotIn("acme", idx)
        self.assertIn("acme", ambiguous)


class TestEntityIndexClassifyLink(unittest.TestCase):
    def setUp(self) -> None:
        self.claroty = _note("entities/customer/claroty.md", aliases=["Claroty Inc"])
        # Simulates a folder rename: the file now lives under person/, not
        # internal-stakeholder/, but old notes still link the old folder.
        self.carlos = _note("entities/person/carlos-quiros.md")
        self.dup_a = _note("entities/customer/acme.md")
        self.dup_b = _note("entities/company/acme.md")
        self.index = EntityIndex([self.claroty, self.carlos, self.dup_a, self.dup_b])

    def test_full_path_exact_match_resolves(self) -> None:
        status, path = self.index.classify_link("entities/customer/claroty")
        self.assertEqual(status, "resolved")
        self.assertEqual(path, "entities/customer/claroty.md")

    def test_stale_full_path_resolves_via_bare_stem(self) -> None:
        # The literal old path no longer exists in the corpus, but the
        # filename stem still uniquely identifies the entity at its new home.
        status, path = self.index.classify_link(
            "entities/internal-stakeholder/carlos-quiros"
        )
        self.assertEqual(status, "resolved")
        self.assertEqual(path, "entities/person/carlos-quiros.md")

    def test_alias_resolves(self) -> None:
        status, path = self.index.classify_link("Claroty Inc")
        self.assertEqual(status, "resolved")
        self.assertEqual(path, "entities/customer/claroty.md")

    def test_colliding_stem_is_ambiguous_not_unresolvable(self) -> None:
        status, path = self.index.classify_link("acme")
        self.assertEqual(status, "ambiguous")
        self.assertIsNone(path)

    def test_unknown_link_is_unresolvable(self) -> None:
        status, path = self.index.classify_link("totally-unknown-entity")
        self.assertEqual(status, "unresolvable")
        self.assertIsNone(path)

    def test_resolve_bare_or_path_only_returns_on_resolved(self) -> None:
        self.assertEqual(
            self.index.resolve_bare_or_path("entities/customer/claroty"),
            "entities/customer/claroty.md",
        )
        self.assertIsNone(self.index.resolve_bare_or_path("acme"))
        self.assertIsNone(self.index.resolve_bare_or_path("totally-unknown-entity"))


if __name__ == "__main__":
    unittest.main()
