#!/usr/bin/env python3
"""Generate TypeScript types from Pydantic MCP App contracts."""
from __future__ import annotations

from pathlib import Path

from src.apps.contracts.debrief import DebriefFormPayload
from src.apps.contracts.lint_queue import LintApplyResult, LintQueuePayload
from src.apps.contracts.prep_card import PrepCardPayload
from src.apps.contracts.snapshot import SnapshotGridPayload
from src.apps.contracts.triage import TriageBoardPayload

OUT = Path(__file__).resolve().parents[1] / "apps" / "packages" / "shell" / "contracts.ts"

MODELS = [
    ("PrepCardPayload", PrepCardPayload),
    ("LintQueuePayload", LintQueuePayload),
    ("LintApplyResult", LintApplyResult),
    ("SnapshotGridPayload", SnapshotGridPayload),
    ("DebriefFormPayload", DebriefFormPayload),
    ("TriageBoardPayload", TriageBoardPayload),
]


def main() -> None:
    lines = [
        "/** Auto-generated from src/apps/contracts — do not edit by hand. */",
        "/* eslint-disable */",
        "",
    ]
    for name, model in MODELS:
        schema = model.model_json_schema()
        # Emit a minimal interface-ish type alias from JSON schema title
        lines.append(f"// JSON Schema for {name}")
        lines.append(f"export type {name} = { _schema_to_ts(schema) };")
        lines.append("")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT}")


def _schema_to_ts(schema: dict) -> str:
    """Very small JSON-schema → TS structural type (good enough for field names)."""
    defs = schema.get("$defs") or schema.get("definitions") or {}
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    if not props and "$ref" in schema:
        ref = schema["$ref"].rsplit("/", 1)[-1]
        target = defs.get(ref, {})
        return _schema_to_ts({**target, "$defs": defs})
    parts = []
    for key, spec in props.items():
        opt = "" if key in required else "?"
        parts.append(f"  {key}{opt}: {_prop_type(spec, defs)};")
    return "{\n" + "\n".join(parts) + "\n}"


def _prop_type(spec: dict, defs: dict) -> str:
    if "$ref" in spec:
        ref = spec["$ref"].rsplit("/", 1)[-1]
        return _schema_to_ts({**defs.get(ref, {"type": "object"}), "$defs": defs})
    if "anyOf" in spec:
        return " | ".join(_prop_type(s, defs) for s in spec["anyOf"])
    t = spec.get("type")
    if t == "string":
        if "enum" in spec:
            return " | ".join(repr(x) for x in spec["enum"])
        return "string"
    if t == "integer" or t == "number":
        return "number"
    if t == "boolean":
        return "boolean"
    if t == "array":
        return f"Array<{_prop_type(spec.get('items') or {}, defs)}>"
    if t == "object" or "properties" in spec:
        return _schema_to_ts({**spec, "$defs": defs})
    if t == "null":
        return "null"
    return "unknown"


if __name__ == "__main__":
    main()
