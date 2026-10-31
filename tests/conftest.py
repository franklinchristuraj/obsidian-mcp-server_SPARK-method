"""Shared test isolation for auth state.

Several suites drive `src.auth` by mutating process-global env
(`WORKSPACE_KEYS_PATH`, `MCP_API_KEY`, `MCP_REQUIRE_AUTH`) plus the module-level
workspace-config cache. When those aren't restored, they leak across files in
collection order: `MCP_API_KEY` gets popped rather than reset, and every later
suite that authenticates with `Bearer test-key` starts returning 401. Snapshot
and restore around every test so file order can't matter.
"""
from __future__ import annotations

import os

import pytest

from src import auth as auth_mod

# Everything verify_api_key reads out of the environment.
_AUTH_ENV = (
    "WORKSPACE_KEYS_PATH",
    "MCP_API_KEY",
    "MCP_REQUIRE_AUTH",
    "MCP_DEFAULT_WORKSPACE_SCOPES",
)


@pytest.fixture(autouse=True)
def _isolate_auth_env():
    """Restore auth env + config cache after each test, however it exits."""
    saved = {name: os.environ.get(name) for name in _AUTH_ENV}
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        auth_mod.clear_workspace_config_cache()
