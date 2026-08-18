"""Tests for MRTR destructive write confirmations."""
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from src import request_context
from src.mrtr import (
    ALWAYS_GATED,
    build_input_required,
    gate_destructive_call,
    mint_request_state,
    needs_confirmation,
    validate_request_state,
)
from src.request_context import RequestMeta
from src.scope import WorkspaceContext, workspace_ctx


class TestNeedsConfirmation(unittest.TestCase):
    def test_always_gated(self) -> None:
        for name in ALWAYS_GATED:
            self.assertTrue(needs_confirmation(name, {}))

    def test_lint_vault_fix_true(self) -> None:
        self.assertTrue(needs_confirmation("lint_vault", {"fix": True}))

    def test_lint_vault_fix_false(self) -> None:
        self.assertFalse(needs_confirmation("lint_vault", {"fix": False}))
        self.assertFalse(needs_confirmation("lint_vault", {}))

    def test_read_tools_not_gated(self) -> None:
        self.assertFalse(needs_confirmation("ping", {}))
        self.assertFalse(needs_confirmation("read_note", {"path": "x.md"}))


class TestRequestState(unittest.TestCase):
    def test_roundtrip(self) -> None:
        args = {"path": "a.md", "scope": "work"}
        state = mint_request_state(
            identity="key:a", tool_name="delete_note", arguments=args
        )
        ok, err = validate_request_state(
            state, identity="key:a", tool_name="delete_note", arguments=args
        )
        self.assertTrue(ok, err)

    def test_identity_mismatch(self) -> None:
        args = {"path": "a.md"}
        state = mint_request_state(
            identity="key:a", tool_name="delete_note", arguments=args
        )
        ok, err = validate_request_state(
            state, identity="key:b", tool_name="delete_note", arguments=args
        )
        self.assertFalse(ok)
        self.assertIn("identity", err)

    def test_args_mismatch(self) -> None:
        state = mint_request_state(
            identity="key:a", tool_name="delete_note", arguments={"path": "a.md"}
        )
        ok, err = validate_request_state(
            state,
            identity="key:a",
            tool_name="delete_note",
            arguments={"path": "b.md"},
        )
        self.assertFalse(ok)
        self.assertIn("arguments", err)


class TestGate(unittest.TestCase):
    def setUp(self) -> None:
        self.auth = WorkspaceContext(
            identity="key:test",
            allowed_scopes=("work",),
            role="user",
            write_scopes=("work",),
        )
        self.modern = RequestMeta(
            protocol_version="2026-07-28",
            is_modern=True,
            client_capabilities={"elicitation": {}},
        )

    def test_first_call_input_required(self) -> None:
        token_w = workspace_ctx.set(self.auth)
        token_m = request_context.request_meta.set(self.modern)
        try:
            result = gate_destructive_call(
                "delete_note",
                {"path": "x.md", "scope": "work"},
                {"name": "delete_note", "arguments": {"path": "x.md", "scope": "work"}},
                self.modern,
            )
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result.get("resultType"), "input_required")
            self.assertIn("requestState", result)
        finally:
            workspace_ctx.reset(token_w)
            request_context.request_meta.reset(token_m)

    def test_retry_with_confirm_proceeds(self) -> None:
        args = {"path": "x.md", "scope": "work"}
        state = mint_request_state(
            identity="key:test", tool_name="delete_note", arguments=args
        )
        token_w = workspace_ctx.set(self.auth)
        try:
            result = gate_destructive_call(
                "delete_note",
                args,
                {
                    "name": "delete_note",
                    "arguments": args,
                    "requestState": state,
                    "inputResponses": {"confirm": {"confirm": True}},
                },
                self.modern,
            )
            self.assertIsNone(result)
        finally:
            workspace_ctx.reset(token_w)

    def test_retry_confirm_false(self) -> None:
        args = {"path": "x.md", "scope": "work"}
        state = mint_request_state(
            identity="key:test", tool_name="delete_note", arguments=args
        )
        token_w = workspace_ctx.set(self.auth)
        try:
            result = gate_destructive_call(
                "delete_note",
                args,
                {
                    "name": "delete_note",
                    "arguments": args,
                    "requestState": state,
                    "inputResponses": {"confirm": {"confirm": False}},
                },
                self.modern,
            )
            self.assertIsNotNone(result)
            assert result is not None
            self.assertTrue(result.get("isError"))
        finally:
            workspace_ctx.reset(token_w)

    def test_legacy_client_blocked(self) -> None:
        legacy = RequestMeta(protocol_version="2025-06-18", is_modern=False)
        token_w = workspace_ctx.set(self.auth)
        try:
            result = gate_destructive_call(
                "delete_note",
                {"path": "x.md"},
                {"name": "delete_note", "arguments": {"path": "x.md"}},
                legacy,
            )
            self.assertIsNotNone(result)
            assert result is not None
            self.assertTrue(result.get("isError"))
            self.assertIn("MRTR", result["content"][0]["text"])
        finally:
            workspace_ctx.reset(token_w)

    def test_lint_fix_false_not_gated(self) -> None:
        token_w = workspace_ctx.set(self.auth)
        try:
            result = gate_destructive_call(
                "lint_vault",
                {"scope": "work", "fix": False},
                {"name": "lint_vault", "arguments": {"scope": "work", "fix": False}},
                self.modern,
            )
            self.assertIsNone(result)
        finally:
            workspace_ctx.reset(token_w)


class TestGateInHandler(unittest.IsolatedAsyncioTestCase):
    async def test_handler_returns_input_required(self) -> None:
        from src.mcp_server import mcp_handler

        auth = WorkspaceContext(
            identity="key:test",
            allowed_scopes=("work",),
            role="user",
            write_scopes=("work",),
        )
        modern = RequestMeta(protocol_version="2026-07-28", is_modern=True)
        token_w = workspace_ctx.set(auth)
        token_m = request_context.request_meta.set(modern)
        try:
            with patch.object(
                mcp_handler, "_run_obsidian_tool", new=AsyncMock()
            ) as mock_run:
                result = await mcp_handler._handle_tools_call(
                    {
                        "name": "delete_note",
                        "arguments": {"path": "x.md", "scope": "work"},
                    }
                )
                mock_run.assert_not_called()
            self.assertEqual(result.get("resultType"), "input_required")
        finally:
            workspace_ctx.reset(token_w)
            request_context.request_meta.reset(token_m)


if __name__ == "__main__":
    unittest.main()
