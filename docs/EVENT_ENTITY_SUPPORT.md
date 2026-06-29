# Event Entity Support + Retrieval/Authoring Improvements

Date: 2026-06-29

This change makes the vault's new `event` entity a first-class, queryable graph
node in the MCP server and adds a set of retrieval and note-authoring
improvements that build on it.

> Scope note: the vault/docs rollout items that live outside this repo
> (`CLAUDE.md` entity registry, `work/index.md` Events catalog, the
> `franklin-obsidian-vault` skill's Entity Layer section) are **not** part of
> this change and are tracked separately.

---

## 1. Event entity model

Event cards live at `entities/event/{YYYY-MM-DD}-{slug}-{event_type}.md` and
represent a single interaction (call, build session, presentation, etc.) as a
graph node.

### Frontmatter schema (required keys)

`entity_type`, `event_type`, `event_date`, `agent_context`, `last_updated`
(plus optional `aliases`, `customer`, `organizations`, `participants`,
`concepts`, `source_note`, `poc_stage`, `source_count`).

Unlike legacy entities, event cards intentionally omit `type` / `created` /
`tags`. Required-field validation is therefore per-`entity_type` — see
`required_fm_for()` in [parser.py](../src/vault_intelligence/parser.py).

### `event_type` controlled vocabulary (9 values)

`discovery-call`, `build-with-me`, `poc-presentation`, `workshop`,
`internal-sync`, `all-hands`, `demo`, `partner-review`, `other`
(constant `EVENT_TYPES` in [parser.py](../src/vault_intelligence/parser.py)).

### Graph edges are frontmatter-sourced

An event's edges (`customer`, `organizations`, `participants`, `concepts`) live
in frontmatter, not the body. The parser now extracts wikilinks from raw
frontmatter into `outlinks` (and a dedicated `frontmatter_links` field) so an
event is reachable as a backlink of the orgs/people/concepts it references.

### Wikilink styles (both resolve)

Event cards use **bare** links (`[[claroty]]`); legacy cards use **full-path**
links (`[[entities/customer/claroty.md]]`). The intelligence tools resolve both
to the canonical path via a stem/alias index (`corpus.index_by_name()` +
`_resolve_link()`), so connections, backlinks, and `lint_vault` treat them
interchangeably.

### `## Events` back-reference block

Customer / company / partner / person / internal-stakeholder cards carry an
idempotent `## Events` block (one `[[event]]` per line, date-descending).
`resolve_entity` / `get_dossier` surface this as an `events` list.

---

## 2. Tool changes

### `create_event` (new)

Creates a schema-valid event card from structured fields and updates back-refs.

- Builds the canonical `YYYY-MM-DD-{slug}-{event_type}.md` filename (customer
  slug when customer-facing, else org slug; collisions get `-2`, `-3` suffixes).
- Writes schema-valid frontmatter (bare wikilink edges) and a
  `# title` / `> agent_context:` / `## Connections` / `## Outcome` body.
- Validates `event_type` against the controlled vocabulary.
- By default idempotently adds the `## Events` back-ref to the linked customer,
  participants, and non-home organizations (home orgs `make`/`celonis` are
  excluded). Back-ref writes leave existing frontmatter byte-for-byte untouched.

Example:

```json
{
  "name": "create_event",
  "arguments": {
    "event_type": "discovery-call",
    "event_date": "2026-06-01",
    "customer": "Claroty",
    "participants": ["Julien"],
    "agent_context": "First discovery call about an OT security POC.",
    "scope": "work"
  }
}
```

### `search` — corpus-backed and ranked

Previously listed every note and re-read each body over REST per call. It now
runs over the mtime-cached corpus and ranks results: title/alias matches >
`agent_context` > frontmatter values > body occurrences. Returns `agent_context`,
`score`, and a match snippet.

### `query_frontmatter` — list membership + range operators

`filters` values now support:

- scalar (wikilink-aware exact match), e.g. `{event_type: "discovery-call"}`
- list membership, e.g. `{participants: "julien"}` (matches a list field)
- comparison objects `{gte|lte|gt|lt|eq|ne: ...}`, e.g.
  `{event_date: {gte: "2026-04-01", lte: "2026-06-30"}}`

### `resolve_entity` / `get_dossier`

- Add an `events` list (from the `## Events` block, sorted by `event_date` desc).
- Connections/backlinks now include the target's `entity_type` (and `event_date`
  when present).
- `key_frontmatter` surfaces `event_type`, `event_date`, `customer`.
- Fuzzy matching now considers aliases, not just filename stems.

### `lint_vault`

- Per-`entity_type` required-field checks (events validated against their schema).
- Flags `event_type` values outside the controlled vocabulary (`invalid_event_type`).
- Broken-link detection resolves bare and full-path links, so bare event links
  are no longer false positives.

### `create_note` / `update_note` — authoring safety

- `create_note` can scaffold an `entities/event/` card (template routing +
  built-in default frontmatter/body).
- Both tools emit non-blocking `validation_warnings` for entity writes (missing
  required fields, out-of-vocab `event_type`).
- `update_note` now preserves/merges frontmatter for any `entities/…` card
  (previously only SPARK folders), protecting the hand-maintained graph from
  accidental clobbering.

---

## 3. Files changed

| File | Change |
|---|---|
| [src/vault_intelligence/parser.py](../src/vault_intelligence/parser.py) | Frontmatter-link extraction, `frontmatter_links`, fast-regex `event_type`/`event_date`, `required_fm_for()`, `EVENT_TYPES`, `EVENTS_HEADING` |
| [src/vault_intelligence/corpus.py](../src/vault_intelligence/corpus.py) | `index_by_name()` stem/alias index for bare-link resolution |
| [src/vault_intelligence/tools.py](../src/vault_intelligence/tools.py) | `_resolve_link`, ranked `search_notes_ranked`, list/range query matchers, events list, entity_type on connections/backlinks, fuzzy alias, per-type + vocab + resolver-aware lint |
| [src/tools/obsidian_tools.py](../src/tools/obsidian_tools.py) | `create_event` tool + dispatch, `_upsert_events_section`, `_entity_write_warnings`, corpus-backed `keyword_search`, entity-card preservation in `update_note` |
| [src/utils/template_utils.py](../src/utils/template_utils.py) | `entities/event/` template routing + default frontmatter/body |
| [src/prompts/obsidian_prompts.py](../src/prompts/obsidian_prompts.py) | Agent guide: event entity, vocab, `## Events`, link styles, query operators, `create_event` workflow |
| [tests/test_vault_intelligence.py](../tests/test_vault_intelligence.py) | Self-contained tests (temp vault + fake client) for all of the above |

---

## 4. Tests

Run the offline-safe suite:

```bash
.venv/bin/python -m pytest tests/test_vault_intelligence.py tests/test_tool_registry_contract.py -q
```

New coverage: bare-link resolution, frontmatter-link backlinks, event
`query_frontmatter` (type + list membership + date range), ranked search, fuzzy
alias, connection `entity_type`, per-type lint, the `_upsert_events_section`
helper, and an end-to-end `create_event` flow with back-ref writes.

> The `TestParseNote` / `TestVaultIntelligenceTools` cases require a live
> `OBSIDIAN_VAULT_PATH` with the GoJob fixture and will fail when that vault is
> not mounted; this is environmental and unrelated to these changes.
