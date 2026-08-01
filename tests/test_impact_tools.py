"""Behavioral contract tests for the Impact System MCP tools."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.vault_intelligence.tools import (
    VaultIntelligenceTools,
    _paired_atomic_write,
)


ENGAGEMENT = """---
type: engagement
date: 2026-02-01
org_id: 0011a00000XXXXX
engagement_type: workshop
why_called: adoption
owning_ve: "[[franklin]]"
customer: "[[acme]]"
arr_at_intake: 500000
outcome_amount: 186000
outcome_corroborated: true
followup_1: 2099-01-01
status: live
agent_context: "Customer-specific private context."
tags: [engagement]
---

# Acme workshop
"""


class TestImpactTools(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        engagements = self.root / "work" / "12_engagements"
        engagements.mkdir(parents=True)
        self.engagement_path = "12_engagements/2026-02-01_acme-workshop.md"
        (self.root / "work" / self.engagement_path).write_text(
            ENGAGEMENT, encoding="utf-8"
        )
        self.tools = VaultIntelligenceTools(str(self.root))

    async def asyncTearDown(self) -> None:
        self._tmp.cleanup()

    async def _capture(self, day: str, scenarios: int, **metrics: object) -> dict:
        result = await self.tools.capture_snapshot(
            org_id="0011a00000XXXXX",
            date=day,
            metrics={"scenarios": scenarios, **metrics},
            source="c360",
            mode="live",
        )
        return result["metadata"]

    async def test_capture_snapshot_is_idempotent_paired_write(self) -> None:
        created = await self._capture("2026-02-01", 10)
        updated = await self._capture("2026-02-01", 12)

        directory = (
            self.root / "work" / "12_engagements" / "_snapshots" / "0011a00000XXXXX"
        )
        self.assertEqual(created["operation"], "created")
        self.assertEqual(updated["operation"], "updated")
        self.assertEqual(len(list(directory.glob("*.json"))), 1)
        self.assertEqual(len(list(directory.glob("*.md"))), 1)
        canonical = json.loads((directory / "2026-02-01.json").read_text())
        self.assertEqual(canonical["scenarios"], 12)
        mirror = (directory / "2026-02-01.md").read_text()
        self.assertIn("type: metric-snapshot", mirror)
        self.assertIn("scenarios: 12", mirror)

    async def test_capture_snapshot_validates_before_writing(self) -> None:
        with self.assertRaisesRegex(ValueError, "date must be YYYY-MM-DD"):
            await self.tools.capture_snapshot(
                org_id="0011a00000XXXXX",
                date="02/01/2026",
                metrics={},
                source="c360",
                mode="live",
            )
        with self.assertRaisesRegex(ValueError, "invalid characters"):
            await self.tools.capture_snapshot(
                org_id="../escape",
                date="2026-02-01",
                metrics={},
                source="c360",
                mode="live",
            )
        self.assertFalse(
            (self.root / "work" / "12_engagements" / "_snapshots").exists()
        )

    def test_paired_write_restores_json_when_markdown_replace_fails(self) -> None:
        directory = self.root / "pair"
        directory.mkdir()
        json_path = directory / "point.json"
        markdown_path = directory / "point.md"
        json_path.write_text("old-json", encoding="utf-8")
        markdown_path.write_text("old-md", encoding="utf-8")
        real_replace = os.replace

        def fail_markdown(source: Path, destination: Path) -> None:
            if Path(destination) == markdown_path and ".tmp-" in Path(source).name:
                raise OSError("simulated failure")
            real_replace(source, destination)

        with patch(
            "src.vault_intelligence.tools.os.replace", side_effect=fail_markdown
        ):
            with self.assertRaisesRegex(OSError, "simulated failure"):
                _paired_atomic_write(json_path, "new-json", markdown_path, "new-md")
        self.assertEqual(json_path.read_text(), "old-json")
        self.assertEqual(markdown_path.read_text(), "old-md")

    async def test_delta_uses_earlier_snapshot_on_equal_distance(self) -> None:
        await self._capture("2026-01-31", 10)
        await self._capture("2026-02-02", 99)
        result = await self.tools.engagement_delta(self.engagement_path, windows=[0])
        window = result["metadata"]["windows"]["0"]
        self.assertEqual(window["date"], "2026-01-31")
        self.assertEqual(window["metrics"]["scenarios"], 10)

    async def test_delta_flags_missing_and_never_bridges_gap(self) -> None:
        await self._capture("2026-01-02", 10)
        await self._capture("2026-02-01", 15)
        await self._capture("2026-05-02", 30)
        result = await self.tools.engagement_delta(self.engagement_path)
        data = result["metadata"]

        self.assertTrue(data["windows"]["+30"]["missing"])
        scenarios = data["deltas"]["scenarios"]
        self.assertEqual(scenarios[0]["abs"], 5)
        self.assertTrue(scenarios[1]["missing"])
        self.assertTrue(scenarios[2]["missing"])

    async def test_delta_handles_zero_and_nonnumeric_metrics(self) -> None:
        await self._capture("2026-01-02", 0, health="red")
        await self._capture("2026-02-01", 10, health="green")
        result = await self.tools.engagement_delta(
            self.engagement_path, windows=[-30, 0]
        )
        data = result["metadata"]["deltas"]
        self.assertIsNone(data["scenarios"][0]["pct"])
        self.assertEqual(data["scenarios"][0]["pct_undefined_reason"], "zero_baseline")
        self.assertEqual(data["health"][0]["skipped"], "nonnumeric_or_absent")

    async def test_delta_marks_mixed_live_and_reconstructed_modes(self) -> None:
        await self._capture("2026-01-02", 10)
        await self.tools.capture_snapshot(
            org_id="0011a00000XXXXX",
            date="2026-02-01",
            metrics={"scenarios": 15},
            source="c360",
            mode="reconstructed",
        )
        result = await self.tools.engagement_delta(
            self.engagement_path, windows=[-30, 0]
        )
        interval = result["metadata"]["deltas"]["scenarios"][0]
        self.assertEqual(interval["from_mode"], "live")
        self.assertEqual(interval["to_mode"], "reconstructed")
        self.assertTrue(interval["mixed_mode"])

    async def test_rollup_filters_headline_and_redacts_records(self) -> None:
        await self._capture(
            "2026-01-02",
            10,
            customer_name="Acme",
            arr=500000,
            notes="Acme renewal",
        )
        await self._capture(
            "2026-02-01",
            15,
            customer_name="Acme",
            arr=600000,
            notes="Acme expanded",
        )
        # +30 window snapshot so median deltas populate
        await self._capture("2026-03-03", 20)
        result = await self.tools.impact_rollup(
            from_date="2026-01-01",
            to_date="2026-02-28",
            filters={"engagement_type": "workshop", "owning_ve": "franklin"},
            redact=True,
        )
        data = result["metadata"]
        serialized_record = json.dumps(data["records"][0]).lower()

        self.assertEqual(data["contract_version"], 1)
        self.assertEqual(data["engagement_count"], 1)
        self.assertEqual(data["commercial"]["corroborated_eur"], 186000)
        self.assertEqual(data["pending_follow_up"], 1)
        self.assertIsInstance(data["headline"], dict)
        self.assertIn("text", data["headline"])
        self.assertIn("confidence", data["headline"])
        self.assertIn("streams", data)
        self.assertIn("coverage", data)
        self.assertIn("provenance", data)
        self.assertEqual(data["records"][0]["stream"], "escalation")
        self.assertEqual(data["records"][0]["customer"], None)
        self.assertNotIn("acme", serialized_record)
        self.assertNotIn("engagement_path", data["records"][0])
        self.assertNotIn("owning_ve", data["filters"])
        self.assertIn("scenarios", data["metric_deltas"])
        self.assertEqual(data["metric_deltas"]["scenarios"]["n_30"], 1)
        self.assertIsNotNone(data["metric_deltas"]["scenarios"]["median_pct_30"])

    async def test_rollup_contract_resolves_customer_and_skips_empty_org(self) -> None:
        note_path = self.root / "work" / "12_engagements" / "missing-org.md"
        note_path.write_text(
            "---\n"
            "type: engagement\n"
            "date: 2026-02-15\n"
            "engagement_type: delivery\n"
            "customer: \"[[entities/customer/northwind.md]]\"\n"
            "org_id: \"\"\n"
            "qualification: below-gate\n"
            "status: closed\n"
            "---\n",
            encoding="utf-8",
        )
        result = await self.tools.impact_rollup(
            from_date="2026-01-01",
            to_date="2026-02-28",
            scope="work",
        )
        data = result["metadata"]
        by_type = {r["engagement_type"]: r for r in data["records"]}
        delivery = by_type["delivery"]
        self.assertEqual(delivery["stream"], "owned-delivery")
        self.assertEqual(delivery["customer"], "northwind")
        self.assertIsNone(delivery["owning_ve"])
        # missing org_id wins over below-gate
        self.assertEqual(delivery["delta_status"], "skipped_no_org_id")
        self.assertEqual(data["streams"]["owned-delivery"]["count"], 1)

    async def test_missing_org_id_returns_explicit_flag(self) -> None:
        note_path = self.root / "work" / "12_engagements" / "missing-org.md"
        note_path.write_text(
            "---\ntype: engagement\ndate: 2026-02-01\n---\n", encoding="utf-8"
        )
        result = await self.tools.engagement_delta("12_engagements/missing-org.md")
        self.assertEqual(result["metadata"]["error"], "missing_org_id")


if __name__ == "__main__":
    unittest.main()
