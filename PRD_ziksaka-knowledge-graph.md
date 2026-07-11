# PRD: Ziksaka Knowledge Graph — from entity lookup to a maintained graph system

**Status:** Draft for Franklin's review.
**Depends on:** PRD-obsidian-headless-migration-v2, Phase 2 complete (filesystem-native MCP, shared `VaultCorpus`, write lock). The graph index and all write-time validation build directly on that corpus.
**Mode:** Personal project. Single user, 631 notes, ~145 entity notes in work scope. Every design decision below favors in-process simplicity over infrastructure.

---

## 1. Background / why this exists

Franklin's vault is not a folder of files. It's his operating system: SPARK flow for knowledge, a work knowledge graph with typed entities (customer, partner, person, company, industry, event), automated writers (Make meeting-notes scenario), and MCP tools that Claude uses as its memory layer.

The node layer is already strong: `resolve_entity` (fuzzy matching, aliases, backlinks, Source History), `query_frontmatter` (range operators, wikilink-aware), `get_dossier` (depth-parameterized assembly), `create_event`, `lint_vault`.

The edge layer is not. A lint audit (2026-07-09, work scope) found:

| Finding | Count | Root cause |
|---|---|---|
| Broken wikilinks | 194 | Links are path-based strings in at least 4 conventions (`work/entities/...`, `entities/...`, bare names, relative `02_projects/...`). A folder rename (`internal-stakeholder/` → `person/`) killed every inbound edge. |
| Events missing `agent_context` | 47 of 47 | The Make meeting-notes scenario, the highest-volume automated writer, doesn't follow the note schema. |
| Alias collisions | 1 | No uniqueness enforcement at write time. |
| Coverage gaps | unknown | `resolve_entity("Mindvalley")` fails despite a delivered Build-With-Me engagement. Entities are created opportunistically, not systematically. |

**The core issue:** a knowledge graph is only as good as its edges, and today's edges are room numbers written on sticky notes. When a file moves rooms, the notes point at empty drawers. Meanwhile, graph maintenance is entirely manual, which for a single busy human means it doesn't happen.

## 2. Problem statement

Three gaps, in causal order:
1. **Fragile substrate.** Edges break silently because link resolution is path-exact while writing habits aren't. Every graph tool built on top inherits this rot.
2. **No edge layer.** There is no way to ask "who is connected to X and how," "what path links A to B," or "what touched this entity since April" without reading files manually. Edges are untyped, so even a traversal can't distinguish "works at" from "mentioned once."
3. **No maintenance loop.** Hygiene (missing fields, broken links, uncreated entities, stale cards) depends on Franklin noticing. It should depend on a systematic agent noticing, with Franklin only approving.

## 3. Goals

1. Edges become first-class: typed, queryable, traversable, resilient to file moves.
2. Retrieval becomes graph-augmented: from "find a note" to "assemble the right context within a budget."
3. Maintenance becomes agentic: a local LLM runs systematically (nightly) to keep node and edge health on track, with human approval at semantic checkpoints, not micro-steps.
4. The existing MCP tool surface stays backward-compatible. New tools are added; existing signatures don't change.

**Non-goals:**
- No graph database (Neo4j, Kuzu, etc.). At this scale an in-memory index rebuilt from files is simpler, and the files remain the single source of truth.
- No embeddings/vector store in this PRD. Keyword search + graph expansion first; a decision gate at the end revisits this.
- No cloud LLM in the maintenance loop. Local model only, by design (cost, privacy for work-scope content, and it's the right dogfooding story for Frank About AI).
- No changes to personal-scope journaling workflows. Rollout starts and stays in `work/entities/` until proven.

## 4. Data model decisions (decide once, before code)

### 4.1 Canonical edges live in frontmatter
Frontmatter is already half-used for edges (`organizations:`, `attendees:`) and `query_frontmatter` is already wikilink-aware. Make it official:
- **Frontmatter relationship fields = machine-readable, typed edges.** Lists of wikilinks under typed keys.
- **`## Connections` = human narrative.** Kept, linted for existence, parsed as untyped `related_to` edges, but never authoritative for type.

```yaml
---
type: person
entity_type: person
works_at: "[[make-company]]"
part_of: ["[[ai-transformation-motion]]"]
agent_context: "Carlos Quiros — Franklin's manager, VE org"
---
```

### 4.2 Controlled edge vocabulary
Small, closed set, enforced by lint. Proposed starting set (Franklin to trim/extend):
- `works_at` (person → company)
- `part_of` (person/team → team/company; company → group)
- `attended` (person → event) / `attendees` (event → person, inverse)
- `engaged_with` (company ↔ engagement/project)
- `customer_of`, `partner_of` (company → company)
- `related_to` (untyped fallback, also what `## Connections` links map to)

Rule: if a relationship doesn't fit the vocabulary, it goes in `## Connections` prose, not a new frontmatter key. New edge types require a deliberate vocabulary change, not an improvised key.

### 4.3 Name-based identity, not path-based
An entity's identity is its canonical name + aliases (already in frontmatter), resolved by the same fuzzy resolver `resolve_entity` uses. Paths are storage detail. Every link parser in the system resolves through the entity index, so `[[franklin-christuraj]]`, `[[work/entities/person/franklin-christuraj]]`, and `[[Franklin Christuraj]]` are the same edge.

### 4.4 Provenance on machine-written data
Any field or edge written by automation carries provenance, so a hallucinated edge is traceable and bulk-revertible:

```yaml
maintenance:
  last_reviewed: 2026-07-10
  provenance: llm-proposed   # human / system / llm-proposed / llm-approved
```

## 5. Architecture overview

```
Layer 4  Maintenance agent (local LLM, nightly)  — proposes, human approves
Layer 3  Context assembly (build_context)         — graph-augmented retrieval
Layer 2  Graph tools (neighbors, backlinks, path, timeline)
Layer 1  Graph index (in-memory, built from VaultCorpus, mtime-invalidated)
Layer 0  Substrate (name-based resolution, write-time validation, lint --fix)
```

Each layer only depends on the one below it. Layers 0-1 are prerequisites for everything; 2, 3, 4 can ship in any order after them (recommended order below).

## 6. Phases

### Phase 0 — Baseline and metrics (half a day)
- Record the lint numbers above as the baseline.
- Coverage audit: cross-reference `12_engagements/` and event attendee/company mentions against existing entity cards; produce the list of missing entities (Mindvalley et al.). This list seeds the maintenance agent's first run later.
- **Acceptance:** a `graph-health.md` note in `work/entities/_meta/` with baseline numbers and the missing-entity list.

### Phase 1 — Substrate hardening (Layer 0)

1. **Name-based link resolution.** Extract the fuzzy resolver from `resolve_entity` into a shared `EntityIndex` (name + aliases → canonical path) inside `vault_intelligence/`. All wikilink parsing (lint, dossier, the new graph index) resolves through it.
2. **`lint_vault --fix` learns link rewriting.** For each broken wikilink, attempt resolution through `EntityIndex`; on unambiguous match, rewrite to canonical form. Ambiguous or unresolvable links go to a report, never auto-guessed. Target: 194 → near 0 in one supervised run.
3. **Write-time validation.** `create_note` / `update_note` / `create_event` resolve outgoing wikilinks on write. Unresolvable links don't block the write (capture speed matters) but are flagged in the tool response and logged to the health note. Alias uniqueness enforced at write time (fixes the collision class).
4. **Fix the Make scenario writer.** The meeting-notes scenario must emit `agent_context` and schema-compliant frontmatter. This is a Make-side change, not MCP-side; do it here because Phase 4's agent shouldn't spend its nights cleaning up after a fixable pipe.
- **Acceptance:** lint shows <5 broken wikilinks; new events arrive schema-complete; a deliberately misspelled link in a test note is flagged at write time.

### Phase 2 — Graph index and edge tools (Layers 1-2)

1. **`GraphIndex`** in `vault_intelligence/graph.py`: adjacency dicts (or networkx if convenient) built from (a) frontmatter relationship fields, (b) `## Connections` links, (c) body wikilinks (weakest, tagged `mention`). Nodes are canonical entity names; edges carry `{type, source_note, provenance}`. Rebuilt lazily on corpus mtime change, same pattern as `VaultCorpus`. At 631 files, full rebuild is milliseconds; no incremental complexity needed.
2. **New MCP tools:**
   - `get_backlinks(name, scope)` — inbound edges with types and source notes.
   - `get_neighbors(name, depth=1, rel_type=None, scope)` — typed traversal. `get_dossier` refactors to use this internally.
   - `find_path(a, b, scope)` — shortest path with edge types ("how do I know this person?").
   - `graph_health(scope)` — lint summary + node/edge/orphan counts, the machine-readable version of the health note. Also the maintenance agent's sensor.
3. **Typed-edge backfill (supervised, one-time):** parse existing `## Connections` and frontmatter into the index; where type is inferable mechanically (event attendees, `organizations:`), promote to typed frontmatter edges with `provenance: system`. Everything else stays `related_to`.
- **Acceptance:** "who attended events with Claroty in the last quarter" answerable in one `get_neighbors` + one `query_frontmatter` call; dossier output unchanged or better; index rebuild <100 ms.

### Phase 3 — Temporal layer (Layer 2, time edges)

Events already carry `event_date` and attendees; the data exists, only the query surface is missing.
- `timeline(name, start?, end?, scope)` — ordered events + note modifications touching an entity.
- `last_touch(name, scope)` — most recent interaction, for "what's gone quiet" queries.
- Extend `get_dossier` with a `since` parameter ("prep me for Gojob, what changed since our last call").
- **Acceptance:** `timeline("gojob")` returns the discovery calls and engagement notes in order without any manual reading.

### Phase 4 — Maintenance agent, "the Custodian" (Layer 4, local LLM)

Franklin's stated approach: a local LLM runs systematically to keep entity notes and graph health on track. Design principles, in his own framework's terms: hierarchical-lite orchestration (a deterministic controller delegates judgment tasks to the model), human in-the-loop at semantic checkpoints, and a hard split between what needs a model and what doesn't.

**Tier 1 — Deterministic (no LLM, cron):**
Nightly: `lint_vault --fix` (safe mechanical fixes), `graph_health` snapshot appended to the health note, coverage re-audit. A regex doesn't hallucinate; never spend tokens on what string matching solves.

**Tier 2 — Judgment (local LLM, nightly batch):**
The controller script assembles small, scoped context packs (one entity or one gap per task, keeping the model far inside its smart zone) and asks the model to:
1. **Draft missing `agent_context`** for legacy notes (one-sentence summaries from note content). Low risk.
2. **Propose entity cards** for names appearing in engagements/events with no card (the Mindvalley class): drafted frontmatter + skeleton body. Medium risk.
3. **Propose typed edges** where evidence exists in note bodies ("Julien Puchol appears in three Gojob events" → `works_at: [[gojob]]`?). Medium risk.
4. **Propose alias merges / duplicate detection.** High risk, proposals only, never auto-applied.
5. **Flag stale cards** (entity with activity in timeline but card body untouched for N months). Zero write risk, pure signal.

**HITL design — the review queue:**
- All Tier 2 output lands in `work/entities/_review/YYYY-MM-DD-proposals.md`: one checkbox per proposal, with evidence quotes and the exact diff to be applied.
- Franklin checks boxes in Obsidian (phone or desktop, anywhere, thanks to Sync). An `apply_approved_proposals` MCP tool (or the next Custodian run) executes checked items and stamps `provenance: llm-approved`.
- **Auto-apply whitelist (starts minimal):** only Tier 1 mechanical fixes. `agent_context` drafts move to auto-apply *only after* the approval rate proves the model out (see metric below). Everything touching edges or creating nodes stays behind the checkbox until further notice.

**Evaluation (agent layer):**
- **Pattern Approval Rate (PAR):** approved / proposed, per task type, logged per run in the health note. PAR ≥ 80% over 4 consecutive weeks on a task type is the promotion criterion for auto-apply. PAR < 50% means the prompt or the task framing is wrong; fix or kill that task type.
- Cost/latency are near-irrelevant (nightly batch, local model), so quality is the only axis that matters.

**Runtime (open decision, see §8):** the controller is a Python script calling an OpenAI-compatible local endpoint, so the model host is swappable: Osaurus on the Mac (Qwen3-class, better quality, machine must be awake) vs. a small quantized model on the VPS CPU (always-on, weaker; the migration just freed 1 GB, but 7.8 GB total means ~4B Q4 territory). Batch latency tolerance makes VPS CPU viable; quality of proposals is the deciding factor. Recommendation: start on the Mac via Osaurus, measure PAR, only consider VPS hosting if the "machine must be awake" constraint actually bites.

- **Acceptance:** after two weeks of nightly runs, zero events missing `agent_context`, the missing-entity list from Phase 0 is drained (as approved cards), PAR is being logged, and Franklin's manual graph maintenance time is ~zero.

### Phase 5 — Context assembly (Layer 3)

`build_context(seed, depth=1, token_budget=4000, scope)`:
1. Resolve seed (entity or free-text via ranked search).
2. Expand: typed neighbors first, `related_to` second, mentions last.
3. Rank: recency (timeline), edge strength (typed > untyped), degree.
4. Compress: `agent_context` lines for periphery, fuller bodies for the core, hard stop at budget.
Returns a structured context pack with a source manifest. This generalizes `get_dossier` and is the SPARK context-manifest concept landing inside the MCP: the vault stops being something Claude searches and becomes something that briefs Claude.
- **Acceptance:** `build_context("claroty", budget=4000)` produces a meeting-ready brief measurably better than `get_dossier` (side-by-side judgment on 5 real prep cases), never exceeding budget.

### Phase 6 — Stabilize and decision gates
- Expand Custodian coverage from `work/entities/` to `passion/` (blueprints registry hygiene is a natural second target).
- **Embeddings gate:** revisit only if (a) vault crosses ~3-5k notes, or (b) FR/EN cross-lingual recall demonstrably fails on real queries. Log failed retrievals in the health note to make this evidence-based, not vibes-based.
- **Graph DB gate:** revisit only if index rebuild exceeds ~1s or multi-user access appears. Neither is plausible soon.

## 7. Risks

1. **LLM-fabricated graph data** is the defining risk of Phase 4. Contained by: proposals-not-writes, evidence quotes in every proposal, provenance stamps, PAR-gated auto-apply promotion, and bulk revert by provenance filter.
2. **The Custodian and Franklin edit concurrently.** Covered by the migration PRD's write lock plus atomic writes; the review-queue design means the agent's writes are batched and small.
3. **Backfill (Phase 2.3) misclassifies edge types.** Supervised one-time run with a dry-run diff, same discipline as the sync-setup dry-run.
4. **Vocabulary creep.** Typed edges only work if the vocabulary stays closed. Lint enforces it; new types require editing the lint config, which is the point: friction as governance.
5. **Local model too weak for proposal quality.** PAR exposes this within weeks, cheaply. Fallback ladder: better prompts → larger local model → narrow the task types. Not: cloud model (non-goal).
6. **Make scenario fix (Phase 1.4) slips** because it's in a different system. If it does, the Custodian compensates, but flag it: fixing producers beats cleaning consumers.

## 8. Open decisions for Franklin

1. **Edge vocabulary:** trim/extend the §4.2 starting set before Phase 2. One-time decision, expensive to churn later.
2. **Custodian runtime:** Mac/Osaurus (recommended start) vs. VPS CPU. Decide by end of Phase 3.
3. **Phase 3 vs Phase 5 order:** current order assumes meeting prep (temporal, dossier) is the primary consumer. If nightly-agent briefings or content research matter more, swap Phases 3 and 5.
4. **Auto-apply promotion threshold:** PAR ≥ 80% over 4 weeks is proposed; adjust appetite.

## 9. Success metrics

- Broken wikilinks: 194 → <5, and stays <5 (Custodian holds the line).
- Entities missing `agent_context`: 47 → 0, and new notes never regress (write-time + producer fix).
- Entity coverage: every company with an engagement or event has a card.
- 100% of machine-written fields carry provenance.
- PAR logged per task type; at least one task type promoted to auto-apply within 8 weeks.
- `build_context` replaces manual note-gathering for meeting prep (5-case side-by-side wins).
- Franklin's manual graph maintenance: ~zero minutes/week after Phase 4.
