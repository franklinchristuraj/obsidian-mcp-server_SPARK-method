# Event Entity Support + Engagement Intelligence

Date: 2026-07-30 (updated from 2026-06-29)

This change makes the vault's `event` entity a first-class, queryable graph
node in the MCP server, and adds parent **engagement** notes for Build-with-Me
adoption programs and technical deep-dive specialist pull-ins.

> Scope note: vault-side agent docs (`CLAUDE.md`, `AGENTS.md`, `work/CLAUDE.md`,
> `franklin-obsidian-vault` / `make-engagement` skills) are kept in sync with
> these tools.

---

## 1. Two-layer model

| Layer | Path | Authoring tool | Role |
|-------|------|----------------|------|
| Engagement (detail) | `12_engagements/YYYY-MM-DD_kebab.md` | **`create_engagement`** | Prep, scorecard, debrief, trial window |
| Event (graph node) | `entities/event/{YYYY-MM-DD}-{slug}-{type}.md` | **`create_event`** | Atomic interaction for timeline / dossier |

Parent ↔ child link: event `parent_engagement` / `source_note` → engagement stem.
`create_event` also upserts the parent's **`## Interactions`** block.

---

## 2. Event entity model

### Frontmatter schema (required keys)

`entity_type`, `event_type`, `event_date`, `agent_context`, `last_updated`
(plus optional `aliases`, `customer`, `organizations`, `participants`,
`concepts`, `source_note`, `poc_stage`, `source_count`, `parent_engagement`,
`touchpoint_type`, `channel`, `adoption_stage`, `requested_by`,
`technical_domains`, `signal_confidence`).

### `event_type` controlled vocabulary (10 values)

`discovery-call`, `build-with-me`, `poc-presentation`, `workshop`,
`internal-sync`, `all-hands`, `demo`, `partner-review`, `technical-deep-dive`,
`other` (constant `EVENT_TYPES` in [parser.py](../src/vault_intelligence/parser.py)).

### Touchpoint / adoption vocabularies

- `touchpoint_type`: `kickoff-workshop`, `email-follow-up`, `mid-trial-review`, `support`, `technical-question`, `final-review`, `ad-hoc`
- `adoption_stage`: `trial-start`, `building`, `mid-trial`, `pre-close`, `converted`, `churned`, `extended`
- `channel`: `workshop`, `call`, `email`, `slack`, `async`, `office-hours`

### Graph edges are frontmatter-sourced

An event's edges (`customer`, `organizations`, `participants`, `concepts`) live
in frontmatter. Parser extracts wikilinks into `outlinks` / `frontmatter_links`.

### `## Events` + `## Interactions` back-refs

- Entity cards: idempotent `## Events` (via `create_event`)
- Engagement notes: idempotent `## Interactions` when `parent_engagement` is set

---

## 3. Engagement model (`create_engagement`)

### `engagement_type` vocabulary

`build-with-me`, `hackathon`, `workshop`, `consulting`, `partner-review`,
`demo`, `ve-assist`, `technical-deep-dive`

### Subtype templates (vault)

| Type | Template |
|------|----------|
| `build-with-me` | `work/00_system/templates/build-with-me-engagement.md` |
| `technical-deep-dive` | `work/00_system/templates/technical-deep-dive.md` |
| `ve-assist` | `work/00_system/templates/ve-assist.md` |
| other | `work/00_system/templates/ve-engagement.md` |

BWM extras: `trial_start`, `trial_end`, `champion`, `sponsor`,
`target_use_cases`, `next_touch`, `next_touch_type`, `adoption_health`,
`adoption_outcome`.

Deep-dive extras: `owning_ve` / `requested_by`, `sales_stage`,
`technical_domains`.

---

## 4. Tool changes

### `create_engagement` (new)

Creates `12_engagements/{date}_{slug}-{engagement_type}.md` from the correct
vault template (built-in fallback if template missing), validates vocabularies,
and optionally appends hub lines to `index.md` / `log.md`.

### `create_event` (extended)

New optional args: `parent_engagement`, `touchpoint_type`, `channel`,
`adoption_stage`, `requested_by`, `technical_domains`, `signal_confidence`.
When `parent_engagement` is set, also updates the parent `## Interactions`
section.

### Retrieval

- `resolve_entity` / `get_dossier` return `engagements` for customers/partners
  (trial window, next touch, adoption health).
- Event connection enrichment includes `touchpoint_type`, `parent_engagement`,
  `adoption_stage`, `technical_domains`, `signal_confidence`.
- `timeline` includes engagement `next_touch` / trial milestones.
- `lint_vault` flags invalid `touchpoint_type` as well as `event_type`.
- `query_frontmatter` can filter engagements and child events by the new fields.

---

## 5. Files changed

| File | Change |
|---|---|
| [src/vault_intelligence/parser.py](../src/vault_intelligence/parser.py) | Vocabs + fast-parsed engagement/event fields |
| [src/vault_intelligence/tools.py](../src/vault_intelligence/tools.py) | Engagements on resolve/dossier/timeline; lint touchpoint |
| [src/tools/obsidian_tools.py](../src/tools/obsidian_tools.py) | `create_engagement`, extended `create_event`, interactions upsert |
| [src/utils/template_utils.py](../src/utils/template_utils.py) | `12_engagements/` routing + engagement builders |
| [src/prompts/obsidian_prompts.py](../src/prompts/obsidian_prompts.py) | Agent guide: parent/child model |
| [tests/test_vault_intelligence.py](../tests/test_vault_intelligence.py) | Engagement + parent-child coverage |

---

## 6. Tests

```bash
.venv/bin/python -m pytest tests/test_vault_intelligence.py tests/test_tool_registry_contract.py tests/test_create_note_templates.py -q
```
