"""Lint apply orchestrator: selective, stale-aware fixes."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List

from src.apps.composers import require_scope
from src.apps.composers.lint_queue import build_findings
from src.apps.contracts.lint_queue import LintApplyResult
from src.tools.obsidian_tools import obsidian_tools
from src.vault_intelligence.corpus import ConcurrentModificationError
from src.vault_intelligence.parser import rewrite_wikilinks


async def apply_lint_findings(scope: str, finding_ids: List[str]) -> Dict[str, Any]:
    scope = require_scope(scope)
    if not finding_ids:
        raise ValueError("finding_ids must be non-empty")

    intel = obsidian_tools._get_vault_intel()
    lint_result = await intel.lint_vault(scope=scope, folder="entities", fix=False)
    lint = json.loads(lint_result["content"][0]["text"])
    findings = await build_findings(scope, lint)
    by_id = {f.id: f for f in findings}

    applied: List[str] = []
    skipped: List[Dict[str, Any]] = []
    stale: List[str] = []

    rewrites_by_note: Dict[str, Dict[str, str]] = {}
    pending_ids_by_note: Dict[str, List[str]] = {}

    for fid in finding_ids:
        finding = by_id.get(fid)
        if finding is None:
            stale.append(fid)
            continue
        if not finding.auto_fixable or not finding.proposed_fix:
            skipped.append({"id": fid, "reason": "not auto-fixable"})
            continue
        if finding.proposed_fix.kind != "rewrite_link":
            skipped.append(
                {"id": fid, "reason": f"unsupported kind {finding.proposed_fix.kind}"}
            )
            continue
        before = finding.proposed_fix.before.strip("[]")
        after = finding.proposed_fix.after.strip("[]")
        rewrites_by_note.setdefault(finding.note_path, {})[before] = Path(after).stem
        pending_ids_by_note.setdefault(finding.note_path, []).append(fid)

    async with intel.corpus.write_lock():
        for note_path, bare in rewrites_by_note.items():
            ids = pending_ids_by_note.get(note_path, [])
            try:
                text = await asyncio.to_thread(intel.corpus.read_text, scope, note_path)
                mtime = await asyncio.to_thread(
                    intel.corpus.stat_mtime, scope, note_path
                )
                new_text, n = rewrite_wikilinks(text, bare)
                if n:
                    await asyncio.to_thread(
                        intel.corpus.write_note,
                        scope,
                        note_path,
                        new_text,
                        create_folders=False,
                        expected_mtime=mtime,
                    )
                    applied.extend(ids)
                else:
                    for fid in ids:
                        skipped.append({"id": fid, "reason": "no rewrite applied"})
            except ConcurrentModificationError:
                for fid in ids:
                    skipped.append({"id": fid, "reason": "concurrent modification"})
            except Exception as e:
                for fid in ids:
                    skipped.append({"id": fid, "reason": str(e)})

    return LintApplyResult(applied=applied, skipped=skipped, stale=stale).model_dump()
