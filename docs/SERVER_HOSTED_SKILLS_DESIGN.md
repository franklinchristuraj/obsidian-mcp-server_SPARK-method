---
type: project
created: 2026-07-30
status: proposed
priority: medium
spark_stage: project
project_goal: "Make the MCP server the single source of truth for agent-facing skill content, so client-side SKILL.md files never need updating when tools change"
success_criteria: "Local SKILL.md contains no tool names or schemas. Tool catalog in vault_mcp_agent_guide is generated from get_tools(). A test fails when a registered tool is missing from the guide or the guide names an unregistered tool."
next_action: "Add group/selection metadata alongside _TOOL_ANNOTATIONS, then build the catalog renderer"
related_areas: []
tags: [project, mcp, skills, documentation]
agent_context: "Design for server-hosted skills: generate the tool catalog from the tool registry, deliver it via the existing vault_mcp_agent_guide prompt, and reduce the client-side SKILL.md to a trigger-only stub so skill drift becomes structurally impossible."
---

# Server-Hosted Skills — Design Document

## Problem Statement

Agent-facing knowledge about this server is duplicated across four places, and every tool change requires a manual edit in each of them:

| Location | Owner | Contains today |
|----------|-------|----------------|
| `src/tools/obsidian_tools.py` — `get_tools()` | code | Canonical tool names, arg names, required/optional, controlled vocabularies, annotations |
| `src/prompts/obsidian_prompts.py` — `vault_mcp_agent_guide` | hand-written prose | Full tool tables restating names, args, and enums |
| `~/.agents/skills/franklin-obsidian-vault/SKILL.md` | hand-written, outside this repo | ~490 lines restating the same tool list, scope rules, and enums, plus a hardcoded "25 tools" count |
| `verify_tools.py` — `expected_tools` | hand-written list | A third copy of the tool name list |

The registry is authoritative but silent. The other three are guesses, and two of them
are already wrong. `get_tools()` registers 26 tools; `verify_tools.py` expects 25 and
omits `rename_note` entirely, and the client-side `SKILL.md` both claims "25 tools" and
leaves `rename_note` out of its tool list. So the tool that exists specifically to stop
agents from orphaning wikilinks is invisible to the skill that is supposed to teach
agents to use it — while the same skill's anti-patterns section warns against the
`delete_note` + `create_note` pattern that `rename_note` replaces.

Nothing detects this. The failure mode is an agent confidently calling a tool name that
no longer exists, passing `query=` to `search` instead of `keyword=`, or never learning
about a tool that shipped months ago.

The client-side `SKILL.md` is the worst offender because it lives outside this repository entirely: a tool rename here has no path to reach it.

## Goal

Move all volatile agent-facing content behind the server, and make the remaining duplication loud instead of silent.

Non-goal: eliminating the local `SKILL.md`. Cursor and Claude decide *whether* to load a skill by reading the `description` frontmatter of a local file, so a local file must exist. The goal is to make its contents stable enough that it never needs editing.

## Target Architecture

Three tiers, split by how often each changes.

### Tier 1 — Local stub (changes ~twice a year)

A trigger-only `SKILL.md`. Frontmatter `description` lists *when* to activate; the body says *where to get the real content*. No tool names, no argument names, no enums, no tool counts.

```markdown
---
name: franklin-obsidian-vault
description: >-
  Franklin Christuraj's Obsidian vault (SPARK PKM across personal, passion, and work
  workspaces). Use for any vault read/write/search, entity resolution, meeting prep,
  capture inbox, VE engagements, infrastructure blueprints, daily notes, stakeholders,
  and OKRs. Served by the Ziksaka MCP server — fetch the operating guide from the
  server before acting.
---

# Franklin's Obsidian Vault

The MCP server is the source of truth for tool names, arguments, scope rules, and
folder conventions. Do not rely on this file for any of them.

**First action, every session:**
1. `prompts/get` → `vault_mcp_agent_guide`
2. `workspaces` → which scopes this API key may use

If the MCP server is unreachable, say so rather than guessing tool names.
```

That is the entire file. It stays valid across every tool rename, every new tool, and every vocabulary change.

### Tier 2 — Hand-written server prose (changes when conventions change)

`vault_mcp_agent_guide` keeps the judgment content that cannot be derived from schemas:

- Workspace model and routing rules (which scope for which topic)
- Scope semantics for reads vs writes
- Entity graph conventions, wikilink styles, engagements-vs-events distinction
- Recommended workflows and anti-patterns
- Tool *selection* guidance — "prefer `resolve_entity` over `search`+`read_note` loops"

This is the part that already exists and is already good. It stays hand-maintained.

### Tier 3 — Generated tool catalog (changes automatically)

A new renderer builds the tool-reference section of the guide from `obsidian_tools.get_tools()` at request time. Everything mechanical comes from the registry:

- Tool name
- Required arguments, from `inputSchema.required`
- Optional arguments worth naming
- Controlled vocabularies, from each property's `enum`
- Mutation risk, from `annotations.readOnlyHint` / `destructiveHint`

A tool rename, a new argument, or a new `event_type` value propagates with no doc edit.

## Rendering Design

### New module: `src/prompts/tool_catalog.py`

```python
def render_tool_catalog(tools: List[MCPTool]) -> str:
    """Markdown tool reference grouped by category, derived from the registry."""
```

Called from `_get_vault_mcp_agent_guide()`, which splices the result into the
hand-written prose at a fixed marker. The prompt function keeps its signature and
return type, so `prompts/get` needs no changes.

### Grouping metadata

`get_tools()` has no category field, and grouping matters for agent comprehension —
a flat alphabetical list of 26 tools reads much worse than the current
"vault intelligence / general vault" split.

Add a `_TOOL_GROUPS` map next to the existing `_TOOL_ANNOTATIONS` in
`obsidian_tools.py`, keyed by tool name:

```python
_TOOL_GROUPS: Dict[str, str] = {
    "resolve_entity": "intelligence",
    "read_note": "general",
    "capture": "capture",
    ...
}
```

Per-tool metadata already lives in that file, so this keeps one place to touch when
adding a tool, and the renderer stays dumb. The renderer raises on an unknown tool
name rather than silently dumping it into a fallback group — a new tool should force
an explicit grouping decision.

### Argument rendering rules

- Required args in **bold**, optional in plain text.
- `scope` is omitted per-tool; the shared read/write scope rule is stated once in the
  prose. Repeating it 26 times wastes tokens.
- `enum` values are rendered inline, capped at a threshold (say 12) with an ellipsis
  beyond it, so the 10-value `event_type` vocabulary appears in full but a large enum
  cannot blow up the prompt.
- `annotations.destructiveHint: true` renders a marker so agents can see which calls
  overwrite or remove data without reading the whole description.

### Token budget

The current guide is roughly 170 lines. The generated catalog should be *more*
compact than the hand-written tables it replaces: one row per tool, no prose
duplication of what the prose already says. Selection guidance stays in Tier 2 and is
not repeated per-row.

## Anti-Drift Verification

This is the part that makes the design hold. Without it, Tier 2 prose drifts from the
registry exactly as it does today.

Add `tests/test_prompt_tool_drift.py` with three assertions:

1. **Completeness** — every registered tool name appears in the rendered
   `vault_mcp_agent_guide`. Catches a new tool that nobody documented.
2. **No ghosts** — every backticked identifier in the guide that looks like a tool
   name resolves to a registered tool, or sits in an explicit allowlist (for
   `prompts/get`, `resources/list`, and similar protocol methods). Catches a renamed
   or deleted tool still referenced in prose.
3. **Grouping totality** — `_TOOL_GROUPS` covers exactly the registered tool set, no
   missing and no stale entries.

Fold `verify_tools.py` into the same source of truth while here: its hardcoded
`expected_tools` list is a third copy of the tool names. It should assert against the
registry plus an explicit "these tools must not disappear" allowlist, which is what
the list is actually for.

## What Deliberately Stays Duplicated

Two things cannot move server-side, and pretending otherwise would be the trap:

1. **Skill trigger conditions.** Only the local `SKILL.md` frontmatter decides
   activation. Accepted cost: one stable paragraph.
2. **Offline fallback behavior.** The current skill documents script fallbacks for
   when MCP is unavailable. Content fetched from the server is useless in exactly that
   scenario. Options: keep a short offline section in the stub, or drop the fallback
   and have the agent report the outage. Recommend dropping it — the scripts are a
   separate maintenance burden and a second drift surface.

## Migration Phases

**Phase 1 — Generated catalog.** Add `_TOOL_GROUPS`, build `tool_catalog.py`, splice
into `vault_mcp_agent_guide`, delete the hand-written tool tables it replaces. Add the
drift test. No client changes; the guide just becomes self-updating.

**Phase 2 — Reconcile `verify_tools.py`.** Point it at the registry so the tool name
list exists once.

**Phase 3 — Shrink the local skill.** Replace the ~490-line `SKILL.md` with the stub.
Anything in it that is genuinely vault knowledge rather than server knowledge (SPARK
flow, ontology status values, personal and passion context, workspace routing rules)
either moves into the guide's Tier 2 prose or stays in the vault's own `AGENTS.md`,
which the guide already points at. Decide per section; do not bulk-delete.

**Phase 4 — Optional `skill://` resources.** If the prompt-based delivery proves
unreliable in practice — agents skipping `prompts/get` despite the `instructions`
field — add a `skill://` resource namespace serving the same rendered content, which
is the pattern the Figma MCP server uses. Deferred because it is a second delivery
mechanism for identical content and only worth building if Tier 1's pointer fails.

## Trade-offs and Risks

**Prompts are not auto-loaded.** MCP prompts are typically user-invoked. This design
leans on the server `instructions` field and the local stub to get the agent to fetch
the guide unprompted. It mostly works today but is a convention, not a guarantee. If
an agent skips the fetch it has *less* context than the current fat skill provides —
strictly worse than today for that one call. Phase 4 exists for this.

**Enums outside the schema.** Some controlled vocabularies are validated in
`template_utils` / `obsidian_tools` helpers rather than declared as JSON Schema
`enum`s. Those are invisible to the renderer. Any vocabulary that agents need to know
should be declared in `inputSchema` so it generates; that is a small, worthwhile
cleanup inside Phase 1.

**A generator can produce worse prose than a human.** The current tables carry
judgment ("one call replaces many search/read cycles") that no schema contains. The
split only works if selection guidance stays in Tier 2 rather than being sacrificed
for generation purity.

## Open Questions

1. Should the guide expose a version or content hash so an agent can tell whether the
   cached copy is stale mid-session?
2. Does `work/AGENTS.md` (VE plays) stay vault-side, or move into a work-scoped
   server prompt? It is vault convention rather than server capability, which argues
   for leaving it where it is.
3. Should `franklin-work-vault` (the work-only skill from the workspace rework design)
   get its own scope-filtered rendering, showing only the tools its API key can use?
