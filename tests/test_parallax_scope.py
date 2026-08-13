"""Parallax scope registration: write_scopes fence, work-only rejects, graph."""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from src import auth as auth_mod
from src.scope import (
    KNOWN_SCOPES,
    WorkspaceContext,
    active_scopes_for_read,
    parse_default_workspace_scopes,
    resolve_write_scope,
    workspace_ctx,
)
from src.utils.template_utils import template_detector
from src.vault_intelligence.corpus import VaultCorpus
from src.vault_intelligence.tools import VaultIntelligenceTools


def _parallax_fixture(root: Path) -> None:
    for scope in KNOWN_SCOPES:
        (root / scope).mkdir(parents=True, exist_ok=True)
    tpl = root / "parallax" / "00_system" / "templates"
    tpl.mkdir(parents=True)
    (tpl / "conversation.md").write_text(
        "---\ntype: conversation\nstatus: raw\n---\n# C\n", encoding="utf-8"
    )
    (tpl / "hypothesis.md").write_text(
        "---\ntype: hypothesis\nstatus: open\nkill_condition: \"\"\n---\n# H\n",
        encoding="utf-8",
    )
    (tpl / "seed.md").write_text("---\ntype: seed\n---\n", encoding="utf-8")
    (tpl / "note.md").write_text("---\ntype: note\n---\n", encoding="utf-8")
    org = root / "parallax" / "entities" / "org"
    org.mkdir(parents=True)
    (org / "o-014.md").write_text(
        "---\n"
        "type: entity\n"
        "created: 2026-08-13\n"
        "entity_type: org\n"
        "agent_context: Opaque org o-014\n"
        "tags: [org]\n"
        "aliases: [o-014]\n"
        "---\n"
        "# o-014\n\n"
        "## Connections\n\n"
        "## Source History\n",
        encoding="utf-8",
    )
    (root / "passion" / "01_seeds").mkdir(parents=True)
    (root / "passion" / "01_seeds" / "secret.md").write_text(
        "parallax should not see this from passion-only key\n", encoding="utf-8"
    )
    (root / "parallax" / "01_seeds").mkdir(parents=True)
    (root / "parallax" / "01_seeds" / "marker.md").write_text(
        "unique parallax-token-xyz\n", encoding="utf-8"
    )
    # Lintable parallax notes live outside entities/, so they are only reached
    # when lint_vault defaults to the whole workspace for this scope.
    conv = root / "parallax" / "11_conversations"
    conv.mkdir(parents=True)
    (conv / "not-a-dated-slug.md").write_text(
        "---\ntype: conversation\nstatus: bogus\n---\n# C\n", encoding="utf-8"
    )
    disc = root / "parallax" / "10_discovery"
    disc.mkdir(parents=True)
    (disc / "h-001.md").write_text(
        "---\ntype: hypothesis\nstatus: nonsense\n---\n# H\n", encoding="utf-8"
    )
    # Links written from the vault root, the way Obsidian renders full paths.
    (root / "parallax" / "charter.md").write_text(
        "---\ntype: note\n---\n# Charter\n", encoding="utf-8"
    )
    (root / "parallax" / "index.md").write_text(
        "---\ntype: note\n---\n# Index\n\n"
        "- [[parallax/charter.md]]\n"          # own scope, prefixed
        "- [[charter]]\n"                      # bare, already worked
        "- [[passion/01_seeds/secret.md]]\n"   # cross-scope, target exists
        "- [[passion/01_seeds/gone.md]]\n",    # cross-scope, target absent
        encoding="utf-8",
    )


class TestParallaxKnownScopes(unittest.TestCase):
    def test_known_scopes_include_parallax(self) -> None:
        self.assertEqual(
            KNOWN_SCOPES, ("personal", "passion", "work", "parallax")
        )

    def test_default_env_includes_parallax(self) -> None:
        os.environ.pop("MCP_DEFAULT_WORKSPACE_SCOPES", None)
        scopes = parse_default_workspace_scopes()
        self.assertIn("parallax", scopes)

    def test_write_scopes_asymmetric(self) -> None:
        write = ("parallax",)
        self.assertEqual(resolve_write_scope(None, write), "parallax")
        with self.assertRaises(PermissionError):
            resolve_write_scope("passion", write)

    def test_template_paths_parallax(self) -> None:
        p = template_detector.get_template_path_for_folder(
            "11_conversations/2026-08-13_o-014_ops.md",
            workspace_scope="parallax",
        )
        self.assertEqual(
            p, "parallax/00_system/templates/conversation.md"
        )
        candidates = template_detector.get_template_candidate_paths(
            "charter.md", workspace_scope="parallax"
        )
        self.assertIn("parallax/00_system/templates/note.md", candidates)


class TestWriteScopesAuth(unittest.TestCase):
    def setUp(self) -> None:
        auth_mod.clear_workspace_config_cache()

    def tearDown(self) -> None:
        auth_mod.clear_workspace_config_cache()

    def test_write_scopes_from_json(self) -> None:
        cfg = {
            "keys": {
                "px-key": {
                    "name": "Parallax agent",
                    "scopes": ["personal", "passion", "work", "parallax"],
                    "write_scopes": ["parallax"],
                    "role": "agent",
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
            os.environ["MCP_API_KEY"] = "px-key"
            os.environ["MCP_REQUIRE_AUTH"] = "true"

            async def run() -> WorkspaceContext:
                req = MagicMock()
                req.query_params.get.return_value = None
                req.headers.get.return_value = None
                req.headers = {"authorization": "Bearer px-key"}
                return await auth_mod.verify_api_key(
                    req, authorization="Bearer px-key"
                )

            ctx = asyncio.run(run())
            self.assertIn("parallax", ctx.allowed_scopes)
            self.assertEqual(ctx.effective_write_scopes, ("parallax",))
        finally:
            os.unlink(path)
            os.environ.pop("WORKSPACE_KEYS_PATH", None)
            os.environ.pop("MCP_API_KEY", None)
            os.environ.pop("MCP_REQUIRE_AUTH", None)


class TestParallaxTools(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="parallax-scope-"))
        _parallax_fixture(self.root)
        os.environ["OBSIDIAN_VAULT_PATH"] = str(self.root)
        from src.clients.obsidian_client import ObsidianClient
        from src.tools.obsidian_tools import ObsidianTools

        self.tools = ObsidianTools()
        self.tools.client = ObsidianClient()
        self.tools.vault_intelligence = VaultIntelligenceTools(
            VaultCorpus(self.root)
        )

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.root, ignore_errors=True)
        token = getattr(self, "_ctx_token", None)
        if token is not None:
            workspace_ctx.reset(token)

    def _drop_parallax_entity_cards(self) -> None:
        """Model the real vault, where parallax/entities/ exists but is empty.

        The fixture seeds an org card there for the graph tests; with cards
        present lint narrows to that tree, which is not the shape we want to
        assert the workspace-wide default against.
        """
        import shutil

        shutil.rmtree(self.root / "parallax" / "entities", ignore_errors=True)
        (self.root / "parallax" / "entities").mkdir(parents=True, exist_ok=True)

    def _set_ctx(
        self,
        scopes: tuple,
        write_scopes: tuple | None = None,
        identity: str = "test",
    ) -> None:
        self._ctx_token = workspace_ctx.set(
            WorkspaceContext(
                identity=identity,
                allowed_scopes=scopes,
                role="agent",
                write_scopes=write_scopes if write_scopes is not None else scopes,
            )
        )

    async def test_workspaces_lists_parallax_and_write_scopes(self) -> None:
        self._set_ctx(
            ("personal", "passion", "work", "parallax"),
            write_scopes=("parallax",),
        )
        result = await self.tools.tool_workspaces()
        payload = result["metadata"]
        self.assertIn("parallax", payload["scopes"])
        self.assertEqual(payload["write_scopes"], ["parallax"])

    async def test_create_note_parallax_uses_template(self) -> None:
        self._set_ctx(("parallax",))
        result = await self.tools.create_note(
            path="11_conversations/2026-08-13_o-014_head-of-ops.md",
            content="",
            scope="parallax",
            use_template=True,
        )
        meta = result.get("metadata") or {}
        path = self.root / "parallax" / "11_conversations" / "2026-08-13_o-014_head-of-ops.md"
        self.assertTrue(path.is_file(), msg=str(result))
        text = path.read_text(encoding="utf-8")
        self.assertIn("type: conversation", text)

    async def test_parallax_key_cannot_write_passion(self) -> None:
        self._set_ctx(
            ("personal", "passion", "work", "parallax"),
            write_scopes=("parallax",),
        )
        with self.assertRaises(ValueError) as ctx:
            await self.tools.update_note(
                path="01_seeds/secret.md",
                content="hijack",
                scope="passion",
            )
        self.assertIn("Access denied", str(ctx.exception))

    async def test_create_engagement_rejects_parallax(self) -> None:
        self._set_ctx(("personal", "passion", "work", "parallax"))
        with self.assertRaises(ValueError) as ctx:
            await self.tools.create_engagement(
                engagement_type="workshop",
                customer="Acme",
                scope="parallax",
            )
        self.assertIn("work-only", str(ctx.exception).lower())
        work_eng = list((self.root / "work" / "12_engagements").glob("*.md")) if (
            self.root / "work" / "12_engagements"
        ).exists() else []
        self.assertEqual(work_eng, [])

    async def test_capture_snapshot_rejects_parallax(self) -> None:
        self._set_ctx(("work", "parallax"))
        with self.assertRaises(ValueError) as ctx:
            await self.tools.vault_intelligence.capture_snapshot(
                org_id="x",
                date="2026-08-13",
                metrics={"n": 1},
                source="c360",
                mode="live",
                scope="parallax",
            )
        self.assertIn("parallax", str(ctx.exception).lower())

    async def test_lint_vault_parallax(self) -> None:
        """Default (no folder) lint must reach 10_discovery/ and 11_conversations/,
        since parallax keeps no entity cards."""
        self._drop_parallax_entity_cards()
        self._set_ctx(("parallax",))
        result = await self.tools.vault_intelligence.lint_vault(scope="parallax")
        payload = json.loads(result["content"][0]["text"])
        summary = payload["summary"]
        self.assertGreaterEqual(summary["notes_scanned"], 3, msg=str(summary))
        self.assertEqual(summary["invalid_note_status"], 2, msg=str(payload))
        self.assertEqual(summary["missing_kill_condition"], 1, msg=str(payload))
        self.assertEqual(
            summary["invalid_conversation_filename"], 1, msg=str(payload)
        )

    async def test_scope_prefixed_links_are_not_broken(self) -> None:
        """[[parallax/x]] from inside parallax is the same note as [[x]]."""
        self._drop_parallax_entity_cards()
        self._set_ctx(("personal", "passion", "work", "parallax"))
        result = await self.tools.vault_intelligence.lint_vault(scope="parallax")
        payload = json.loads(result["content"][0]["text"])
        broken = {b["link"] for b in payload["broken_wikilinks"]}
        self.assertNotIn("parallax/charter.md", broken, msg=str(broken))
        self.assertNotIn("passion/01_seeds/secret.md", broken, msg=str(broken))
        # A cross-scope link whose target is genuinely absent still reports.
        self.assertIn("passion/01_seeds/gone.md", broken, msg=str(broken))

    async def test_cross_scope_link_not_resolved_outside_read_fence(self) -> None:
        """A parallax-only key must not learn that passion notes exist."""
        self._drop_parallax_entity_cards()
        self._set_ctx(("parallax",))
        result = await self.tools.vault_intelligence.lint_vault(scope="parallax")
        payload = json.loads(result["content"][0]["text"])
        broken = {b["link"] for b in payload["broken_wikilinks"]}
        self.assertIn("passion/01_seeds/secret.md", broken, msg=str(broken))
        self.assertNotIn("parallax/charter.md", broken, msg=str(broken))

    async def test_lint_vault_narrows_to_populated_entities_tree(self) -> None:
        """work holds real cards under entities/, so lint stays scoped to them."""
        cards = self.root / "work" / "entities" / "customer"
        cards.mkdir(parents=True, exist_ok=True)
        (cards / "acme.md").write_text(
            "---\ntype: entity\ncreated: 2026-08-13\nentity_type: customer\n"
            "agent_context: Acme\ntags: [customer]\n---\n"
            "# Acme\n\n## Connections\n\n## Source History\n",
            encoding="utf-8",
        )
        (self.root / "work" / "99_notes").mkdir(parents=True, exist_ok=True)
        (self.root / "work" / "99_notes" / "loose.md").write_text(
            "---\ntype: note\n---\n# L\n", encoding="utf-8"
        )
        self._set_ctx(("work",))
        result = await self.tools.vault_intelligence.lint_vault(scope="work")
        payload = json.loads(result["content"][0]["text"])
        scanned = payload["summary"]["notes_scanned"]
        self.assertEqual(scanned, 1, msg=str(payload))
        self.assertNotIn(
            "99_notes/loose.md", json.dumps(payload), msg="should not leave entities/"
        )

    async def test_lint_vault_scans_scopes_without_entities_tree(self) -> None:
        """passion has no entities/ at all, so it must not scan nothing."""
        self._set_ctx(("passion",))
        result = await self.tools.vault_intelligence.lint_vault(scope="passion")
        payload = json.loads(result["content"][0]["text"])
        self.assertGreaterEqual(
            payload["summary"]["notes_scanned"], 1, msg=str(payload)
        )

    async def test_empty_entities_scaffold_does_not_swallow_the_scan(self) -> None:
        """The real trap: passion/parallax ship an empty entities/ directory."""
        (self.root / "passion" / "entities").mkdir(parents=True, exist_ok=True)
        self._set_ctx(("passion",))
        result = await self.tools.vault_intelligence.lint_vault(scope="passion")
        payload = json.loads(result["content"][0]["text"])
        self.assertGreaterEqual(
            payload["summary"]["notes_scanned"], 1, msg=str(payload)
        )

    async def test_lint_vault_explicit_folder_still_wins(self) -> None:
        self._set_ctx(("parallax",))
        result = await self.tools.vault_intelligence.lint_vault(
            scope="parallax", folder="11_conversations"
        )
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["summary"]["notes_scanned"], 1, msg=str(payload))

    async def test_resolve_and_dossier_org(self) -> None:
        self._set_ctx(("parallax",))
        resolved = await self.tools.vault_intelligence.resolve_entity(
            "o-014", scope="parallax"
        )
        data = json.loads(resolved["content"][0]["text"])
        self.assertEqual(data["entity_type"], "org")
        self.assertEqual(data.get("engagements"), [])

        dossier = await self.tools.vault_intelligence.get_dossier(
            "o-014", scope="parallax"
        )
        d = json.loads(dossier["content"][0]["text"])
        self.assertEqual(d["entity"]["entity_type"], "org")
        self.assertNotIn("error", d)

    async def test_passion_key_search_fence(self) -> None:
        self._set_ctx(("passion",))
        # Unscoped search only sees passion — parallax marker must be absent.
        hits = await self.tools.vault_intelligence.search_notes_ranked(
            "parallax-token-xyz", scope=None, limit=20
        )
        self.assertEqual(hits, [])
        # Explicit parallax scope denied for passion-only key.
        with self.assertRaises(PermissionError):
            active_scopes_for_read("parallax", ("passion",))


if __name__ == "__main__":
    unittest.main()
