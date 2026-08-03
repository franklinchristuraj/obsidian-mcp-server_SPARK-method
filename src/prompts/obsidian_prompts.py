"""
Obsidian MCP Prompts - Template and Format Instructions
Provides AI assistants with context about note templates and formatting rules
"""
from typing import List, Dict, Any, Optional
from ..types import MCPPrompt


class ObsidianPrompts:
    """
    MCP Prompts for Obsidian note templates and formatting guidelines
    """

    def get_prompts(self) -> List[MCPPrompt]:
        """Get all available prompts for note formatting and templates"""
        return [
            MCPPrompt(
                name="vault_mcp_agent_guide",
                description=(
                    "Canonical guide: workspaces, all MCP tools (including vault intelligence), "
                    "scope/paths, entity graph conventions—load this first every session."
                ),
                arguments=[],
            ),
            # Prompt 1: Note Template System Overview
            MCPPrompt(
                name="note_template_system",
                description=(
                    "SPARK-style folders and YAML templates; paths are under a workspace "
                    "(personal/passion/work) when using MCP tools—pair with vault_mcp_agent_guide."
                ),
                arguments=[
                    {
                        "name": "note_type",
                        "description": (
                            "Optional: daily, project, area, seed, resource, or knowledge "
                            "(limits the prompt to that section; omit for the full overview)."
                        ),
                        "required": False,
                    }
                ],
            ),
            # Prompt 2: Daily Note Template
            MCPPrompt(
                name="daily_note_template",
                description=(
                    "Daily note YAML and sections; MCP path is e.g. 06_daily-notes/YYYY-MM-DD.md "
                    "plus scope=personal (or allowed workspace)."
                ),
                arguments=[
                    {
                        "name": "date",
                        "description": "Date for the daily note (YYYY-MM-DD format)",
                        "required": False,
                    }
                ],
            ),
            # Prompt 3: Project Note Template
            MCPPrompt(
                name="project_note_template",
                description=(
                    "Project note YAML under 02_projects/; set MCP scope to the workspace that owns the project."
                ),
                arguments=[
                    {
                        "name": "project_name",
                        "description": "Name of the project",
                        "required": False,
                    }
                ],
            ),
            # Prompt 4: Area Note Template
            MCPPrompt(
                name="area_note_template",
                description=(
                    "Area note YAML under 03_areas/; choose MCP scope (personal/passion/work) from context."
                ),
                arguments=[
                    {
                        "name": "area_name",
                        "description": "Name of the area",
                        "required": False,
                    }
                ],
            ),
            # Prompt 5: Format Preservation Guidelines
            MCPPrompt(
                name="format_preservation_rules",
                description=(
                    "YAML and structure preservation when editing via MCP; paths remain workspace-relative."
                ),
                arguments=[],
            ),
            # Prompt 6: Meeting Prep -> Logging Workflow
            MCPPrompt(
                name="meeting_prep_workflow",
                description=(
                    "End-to-end workflow for a work meeting: brief before the call "
                    "(get_dossier/build_context), log it after (create_event). scope=work."
                ),
                arguments=[
                    {
                        "name": "entity_name",
                        "description": (
                            "Optional: the customer/person/partner name this meeting is "
                            "about, used to make the example calls concrete."
                        ),
                        "required": False,
                    }
                ],
            ),
        ]

    async def get_prompt_content(
        self, prompt_name: str, arguments: Dict[str, Any] = None
    ) -> str:
        """Get the content for a specific prompt"""
        if arguments is None:
            arguments = {}

        if prompt_name == "vault_mcp_agent_guide":
            return self._get_vault_mcp_agent_guide()
        if prompt_name == "note_template_system":
            return self._get_template_system_prompt(arguments.get("note_type"))
        elif prompt_name == "daily_note_template":
            return self._get_daily_note_template(arguments.get("date"))
        elif prompt_name == "project_note_template":
            return self._get_project_note_template(arguments.get("project_name"))
        elif prompt_name == "area_note_template":
            return self._get_area_note_template(arguments.get("area_name"))
        elif prompt_name == "format_preservation_rules":
            return self._get_format_preservation_rules()
        elif prompt_name == "meeting_prep_workflow":
            return self._get_meeting_prep_workflow(arguments.get("entity_name"))
        else:
            raise ValueError(f"Unknown prompt: {prompt_name}")

    def _get_vault_mcp_agent_guide(self) -> str:
        """Single source of truth for agents using workspace-scoped MCP tools."""
        return """# Vault workspaces and MCP tools (agent guide)

## 1. Three workspaces

The vault is split into top-level folders (scopes):

| Scope | Typical use |
|-------|-------------|
| `personal` | Journal, family, finances, health, trips, people |
| `passion` | Research, side projects, content, learning, blueprints |
| `work` | Employer projects, meetings, stakeholders, OKRs, **entity graph** |

Each scope has its own `00_system/templates/`, `01_seeds/`, `02_projects/`, etc. Same relative path in two scopes is **two different notes**.

## 2. Start with `workspaces`

Call the **`workspaces`** tool once per session (or when unsure). It returns which scopes this **API key** may use. Do not assume access to all three.

**Recommended session start:** `workspaces` → load this guide (or vault `AGENTS.md`) → `ping` for health. For entity questions, go straight to vault intelligence tools — not search+read loops.

## 3. Paths and `scope`

- **`path`** arguments are **relative to a workspace**, e.g. `06_daily-notes/2026-04-11.md`, `entities/customer/gojob.md`.
- **Work meeting notes** use **`scope=work`** and paths under **`11_work-meeting-notes/`** (aligned with meeting templates in `template_utils`).
- **Never** put `personal/`, `passion/`, or `work/` as the first segment of `path`. Use the **`scope`** parameter instead.
- **Reads** (search, list, vault intelligence, read): optional `scope`. Omit to include all scopes allowed for this key; set it to narrow to one workspace.
- **Writes** (`create_note`, `update_note`, `append_note`, `delete_note`): if the key has **more than one** allowed scope, **`scope` is required**. If the key has exactly one scope, it is auto-selected.

## 4. Work vault entity graph (read the structure, do not infer it)

The **work** scope includes a hand-maintained knowledge graph under `entities/`:

- **Entity cards** live at `entities/{entity_type}/{kebab-name}.md` (e.g. `entities/customer/gojob.md`).
- **`entity_type`** is one of: `person`, `internal-stakeholder`, `customer`, `partner`, `company`, `concept`, `tool`, `industry`, `use-case`, `event`.
- Most cards have YAML frontmatter: `type`, `created`, `agent_context`, `tags`, `entity_type`, plus optional `aliases`, `poc_stage`, `lifecycle_stage`, etc.
- **`## Connections`** lists related notes as `[[wikilinks]]` (paths workspace-relative, no `work/` prefix).
- **`## Source History`** holds dated mention lines with wikilinks.
- **`agent_context`** is the one-line summary — intelligence tools return this instead of full bodies.

### Engagements vs events

- **Engagements** (detail) live at `12_engagements/YYYY-MM-DD_kebab.md` (`type: engagement`). Prefer **`create_engagement`**.
  - `build-with-me` = parent **adoption program** for a ~1-month enterprise trial (trial window, planned touchpoints, scorecard).
  - `technical-deep-dive` = specialist architecture / advanced use-case pull-in from another VE.
  - `delivery` = owned build-and-ship work (`hours_invested`, `price_charged`, `shipped_date`, `handover_artifact`).
  - `enablement` = coaching a VE to self-serve a topic (`target_ve`, `topic`, `graduated`, `hours_returned_est`).
  - Other types (`hackathon`, `workshop`, `demo`, `partner-review`, `consulting`, `ve-assist`) are usually atomic sessions.
- **Events** (graph nodes) live at `entities/event/{YYYY-MM-DD}-{slug}-{event_type}.md`. Prefer **`create_event`**.
- Child interactions link to parents via `parent_engagement` + `source_note`. Parent notes get an idempotent **`## Interactions`** roll-up.

### Event entities (`entity_type: event`)

- Represent a single interaction (call, build session, email follow-up, support touch, etc.) as a graph node.
- **`event_type`** controlled vocabulary (10 values): `discovery-call`, `build-with-me`, `poc-presentation`, `workshop`, `internal-sync`, `all-hands`, `demo`, `partner-review`, `technical-deep-dive`, `other`.
- Optional BWM/specialist fields: `parent_engagement`, `touchpoint_type` (`kickoff-workshop` / `email-follow-up` / `mid-trial-review` / `support` / `technical-question` / `final-review` / `ad-hoc`), `channel`, `adoption_stage`, `requested_by`, `technical_domains`, `signal_confidence`.
- Required frontmatter: `entity_type`, `event_type`, `event_date`, `agent_context`, `last_updated`. Graph edges are **frontmatter-sourced** (`customer`, `organizations`, `participants`, `concepts`).
- Customer / company / partner / person / internal-stakeholder cards carry an idempotent **`## Events`** back-ref block. `resolve_entity` / `get_dossier` also surface linked `12_engagements/` notes as an `engagements` list (trial window, `next_touch`, adoption health).

### Impact System snapshots

- **`capture_snapshot`** writes an idempotent canonical JSON + Dataview Markdown pair at `12_engagements/_snapshots/{org_id}/{date}`. Required: `org_id`, `date`, schema-free `metrics`, `source`, `mode` (`live` or `reconstructed`); `scope=work`.
- **`engagement_delta`** resolves snapshots around an engagement's `date` using its exact `org_id`. Default windows are `[-30, 0, +30, +90]`; the nearest point within ±14 days is used, equal-distance ties prefer the earlier point, and missing windows are explicit. Modes are propagated and gaps are never interpolated.
- **`impact_rollup`** aggregates deltas for engagements in an inclusive `from`/`to` range. Optional filters (`why_called`, `engagement_type`, `owning_ve`) use AND semantics. `redact=true` returns the identity-safe hosted projection.
- Never infer an `org_id`, hide a missing window, or blend a reconstructed point without preserving its mode.

### Wikilink styles (both resolve)

Event entities use **bare** links (`[[claroty]]`, `[[2026-05-01-claroty-discovery-call]]`) relying on alias/name resolution, while legacy cards use **full-path** links (`[[entities/customer/claroty.md]]`). The vault intelligence tools resolve **both** forms to the canonical path, so connections, backlinks, and `lint_vault` treat them interchangeably.

**Do not** rebuild the graph with repeated `search` + `read_note` when a vault intelligence tool applies.

### Work folder map (MCP paths under `scope=work`)

Key paths: `entities/{entity_type}/` (knowledge graph, including `entities/event/`), `11_work-meeting-notes/` (alias `11_meeting-notes`), `12_engagements/`, `13_feedback/`, `raw/` (read only), `index.md`, `log.md`. Passion-only: `07_blueprints/` (`proj-*` / `tool-*` prefixes). Root capture inbox: vault-root `01_seeds/` via **`capture`** (no scope).

## 5. Which tool when

### Vault intelligence (prefer for work entities — use `scope=work`)

| Goal | Tool | Arguments / notes |
|------|------|-------------------|
| Look up customer, person, partner, concept, event by name or alias | **`resolve_entity`** | `name` (fuzzy/alias OK, e.g. `Gojab` → GoJob); `scope=work`. Returns path, `agent_context`, connections (with target context), backlinks, `events` list, linked `engagements` (BWM programs / deep-dives), recent Source History. **One call replaces many search/read cycles.** |
| Filter by frontmatter (live, not index files) | **`query_frontmatter`** | `filters` object, AND semantics, e.g. `{entity_type: customer, poc_stage: discovery}` or `{entity_type: event, event_type: discovery-call}`; optional `folder`, `tag`; `scope=work`. Returns path + `agent_context` only (max 50). |
| Meeting prep / stakeholder brief | **`get_dossier`** | `name` (same as resolve_entity); `scope=work`; optional `since` (YYYY-MM-DD) adds a `changes_since` block. Wraps resolve_entity + open questions + cross-vault recent mentions + the entity's `events`. |
| Check convention drift | **`lint_vault`** | optional `scope`, `folder` (default `entities`). Read-only unless `fix=true`. |
| Who/what points at an entity, and how | **`get_backlinks`** | `name` (fuzzy/alias OK); `scope=work`. Typed inbound edges (engaged_with/attended/attendees/related_to/mention) with source note + provenance. |
| Typed traversal from an entity | **`get_neighbors`** | `name`; `scope=work`; optional `depth` (default 1), `rel_type` filter, `direction` (out/in/both, default both). Each result carries hop count + edge type(s). |
| "How do I know this person?" — shortest connection path | **`find_path`** | `a`, `b` (fuzzy/alias OK); `scope=work`. Returns the hop chain with edge type at each step. |
| Machine-readable graph health (for scripts/dashboards, not just prose) | **`graph_health`** | optional `scope=work`. `lint_vault` summary + node/edge counts + edge-type histogram + orphans + missing-entity list (event customer/organizations with no matching card). |
| Ordered interaction history for an entity | **`timeline`** | `name`; `scope=work`; optional `start`/`end` (YYYY-MM-DD). Events + dated Source History mentions + connected-note `last_updated` timestamps, newest first. |
| "What's gone quiet" — most recent interaction | **`last_touch`** | `name`; `scope=work`. Latest `timeline` item only. |
| Budget-bounded, graph-augmented context pack (multi-hop research/prep) | **`build_context`** | `seed` (entity name, or free text — falls back to ranked search); `scope=work`; optional `depth` (default 1), `token_budget` (default 4000). Typed neighbors first, then related_to, then mentions; returns a `context_pack` + `source_manifest`. |
| Compare adoption metrics around one engagement | **`engagement_delta`** | `engagement_path`; optional `windows`; `scope=work`. Requires the note's `org_id`. |
| Aggregate engagement impact for a period | **`impact_rollup`** | `from`, `to`; optional AND `filters`, `redact`; `scope=work`. |

After intelligence tools return a **path**, call **`read_note`** only when you need the **full markdown body**.

### General vault tools

| Goal | Tool | Notes |
|------|------|--------|
| See allowed scopes | `workspaces` | No arguments |
| Folder tree + counts | `vault_structure` | Optional `scope` |
| Browse files | `list_notes` | Optional `folder`, `scope`; mtime filters `modified_after`, `modified_before`, `days`, `hours`, `limit` |
| Daily notes in date range | `list_journal` | **`startDate`**, **`endDate`** (YYYY-MM-DD, required); optional `scope` |
| Find text in bodies | `search` | **`keyword`** (required — not `query`); optional `folder`, `scope`. Relevance-ranked (title/alias/agent_context/frontmatter > body). |
| Read one file | `read_note` | `path`; optional `scope` |
| Check existence | `note_exists` | Same pattern as read |
| Create | `create_note` | `path`, `content`; `scope` if multi-scope key |
| Quick-capture to root inbox | **`capture`** | **No scope.** `title`, `content`, `source`, `capture_type` (thought/post/excerpt), `spark`, `captured`. Writes `type: capture` to root `01_seeds/`. |
| Create a VE **engagement** (parent note) | `create_engagement` | `engagement_type` (required); optional `customer`/`partner`, `date`, BWM fields (`trial_start`/`trial_end`/`next_touch`/…), deep-dive fields (`owning_ve`/`requested_by`/`technical_domains`). Writes `12_engagements/`. `scope=work`. |
| Create an **event** entity (child interaction) | `create_event` | `event_type` (required); optional `customer`, `participants`, `parent_engagement`, `touchpoint_type`, `channel`, `adoption_stage`, `requested_by`, `technical_domains`, `outcome`. Updates `## Events` + parent `## Interactions`. `scope=work`. |
| Capture a paired metric snapshot | `capture_snapshot` | `org_id`, `date`, `metrics`, `source`, `mode`; writes JSON + Markdown idempotently; `scope=work`. |
| Replace body | `update_note` | `scope` if multi-scope key |
| Append | `append_note` | `scope` if multi-scope key |
| Delete | `delete_note` | `scope` if multi-scope key |
| Move/rename | `rename_note` | `path`, `new_path` (same workspace); `scope` if multi-scope key. Rewrites `[[wikilinks]]` elsewhere in the workspace to the new stem (`update_backlinks=true`, default) — prefer this over `create_note`+`delete_note`, which leaves backlinks broken. |

Use only registered tool names (legacy `obs_*` names are not available).

### Recommended workflows

**Entity question** (who is GoJob, what's their POC stage?):
1. `resolve_entity(name="Gojab", scope="work")`
2. `read_note` only if the returned `agent_context` / connections are insufficient

**Pipeline / stage query** (all discovery-stage customers):
1. `query_frontmatter(filters={entity_type: customer, poc_stage: discovery}, scope="work", folder="entities")`

**Event / interaction query** (all discovery calls, or a POC timeline):
1. `query_frontmatter(filters={entity_type: event, event_type: discovery-call}, scope="work", folder="entities/event")`
2. For POC pipeline timelines, filter on `poc_stage` and sort/read by `event_date`.
3. For one entity's interactions, use the `events` list from `resolve_entity(name=..., scope="work")`.

**Before a meeting**:
1. `get_dossier(name="gojob", scope="work")` — includes the customer's `events` timeline.

**Starting a Build-with-Me adoption program**:
1. `create_engagement(engagement_type="build-with-me", customer="4flow", date="2026-07-23", trial_start="2026-07-23", trial_end="2026-08-31", next_touch="2026-07-29", next_touch_type="mid-trial-review", scope="work")`
2. Log each touch: `create_event(event_type="build-with-me", touchpoint_type="kickoff-workshop", parent_engagement="2026-07-23_4flow-build-with-me", customer="4flow", scope="work")`

**Logging a technical deep-dive** (specialist pull-in):
1. `create_engagement(engagement_type="technical-deep-dive", customer="Acme", owning_ve="other-ve", technical_domains=["mcp","sap-onprem"], scope="work")`
2. `create_event(event_type="technical-deep-dive", parent_engagement=<stem>, customer="Acme", requested_by="other-ve", scope="work")`

**Logging a new interaction** (call, build session, demo…):
1. `create_event(event_type="discovery-call", customer="GoJob", participants=["Julien"], event_date="2026-06-01", scope="work")` — handles filename, frontmatter, and `## Events` back-refs. Prefer this over hand-building an event card with `create_note`.

**Full meeting cycle** (brief → take the call → log it): load the **`meeting_prep_workflow`** prompt — it chains `get_dossier`/`build_context` before the call with `create_event` after, in one documented flow.

**Renaming/moving an entity or note**:
1. `rename_note(path="entities/customer/old-slug.md", new_path="entities/customer/new-slug.md", scope="work")` — not `delete_note` + `create_note`, which orphans every inbound `[[wikilink]]` until the next `lint_vault(fix=True)`.

**Quick capture** (voice thought, saved post, excerpt — pre-scope inbox):
1. `capture(content="...", source="voice", capture_type="thought")` — no scope needed. Promotion to a workspace happens at weekly triage.

**Free-text grep across notes** (when not entity-centric):
1. `search(keyword="...", scope="work")`

## 6. MCP resources vs tools

- **`resources/list`** returns a **folder map only** (vault root + folders)—not every note. Daily notes, entities, meetings, etc. are *not* individual MCP resources.
- **`resources/read`** still works for any note URI (`obsidian://notes/personal/06_daily-notes/2026-04-11.md`). Prefer the **`obsidian://notes/{+path}`** resource template, or scoped tools.
- Resources are **not** filtered by API-key workspace scope. If the connection is restricted (e.g. work-only key), **prefer scoped tools** (`list_notes`, `read_note`, `search`, `list_journal`, vault intelligence) with `scope` so the server enforces access.

## 7. Claude / Cursor skills (outside this server)

Align user-facing skills with: routing rules (which scope for which topic), tool names above, and “call `workspaces` first.” Work-only assistants should default to **`scope=work`** and vault intelligence tools for entity questions.

Vault-side companion docs: **`AGENTS.md`** (MCP tool catalog), **`CLAUDE.md`** (vault rules and ontology).

## 8. Template prompts

After this guide, use **`note_template_system`** and the type-specific prompts for YAML and section structure. Template paths on disk include the workspace (e.g. `personal/00_system/templates/...`); MCP **`create_note`** resolves templates using the **`scope`** you pass.

For a whole work meeting (brief before, log after), load **`meeting_prep_workflow`** instead — it walks `get_dossier`/`build_context` and `create_event` as one flow rather than one-line tool mentions.

---
*Maintain this prompt when tools or scope rules change; keep it the single agent-facing summary.*
"""

    def _get_template_system_prompt(self, note_type: Optional[str] = None) -> str:
        """Template system overview prompt; optional note_type returns one section + shared rules."""
        full = """# Obsidian Vault Template System

## MCP tools and workspace paths

When using **MCP tools**, note paths are **workspace-relative**: you pass `scope` (e.g. `personal`) and `path` like `06_daily-notes/2026-04-11.md`. The same folder names below exist **inside each** of `personal/`, `passion/`, and `work/` on disk.

For **tool choice, scope rules, and resources vs tools**, load the **`vault_mcp_agent_guide`** prompt first.

---

This vault uses a structured template system with YAML frontmatter for different note types:

## Note Types & Folders

### 1. Daily Notes (06_daily-notes/)
- **Purpose**: Daily reflection and tracking
- **YAML Fields**: creation-date, type, focus, family_presence, learning_progress, well_being, tags
- **Structure**: Date-based filename (YYYY-MM-DD.md)

### 2. Projects (02_projects/)
- **Purpose**: Actionable goals with deadlines and outcomes
- **YAML Fields**: folder, type, created, status, priority, deadline, spark_stage, project_goal, success_criteria, next_action, related_areas, originated_from_seed, tags, agent_context
- **Structure**: Project-specific content with clear outcomes

### 3. Areas (03_areas/)
- **Purpose**: Ongoing life responsibilities requiring continuous attention
- **YAML Fields**: folder, type, created, status, area_type, spark_stage, responsibility_level, review_frequency, related_projects, key_metrics, originated_from_seed, tags, agent_context
- **Structure**: Responsibility-focused with regular review cycles

### 4. Seeds (01_seeds/)
- **Purpose**: Initial ideas and concepts that may grow into projects or areas
- **Structure**: Simple notes that can be promoted to projects/areas

### 5. Resources (04_resources/)
- **Purpose**: External knowledge and reference materials
- **Structure**: Curated reference library with source attribution

### 6. Knowledge (05_knowledge/)
- **Purpose**: Personal insights and learned concepts
- **Structure**: Structured knowledge base

### 7. Work meeting notes (11_work-meeting-notes/)
- **Purpose**: Meeting documentation in the work scope
- **MCP path**: `11_work-meeting-notes/YYYY-MM-DD_kebab.md` with `scope=work`
- **Alias**: `11_meeting-notes` is accepted by the MCP template engine

### 8. Event entities (entities/event/) — work scope only
- **Purpose**: Single interactions as knowledge-graph nodes (calls, demos, build sessions)
- **MCP path**: `entities/event/YYYY-MM-DD-{slug}-{event_type}.md` with `scope=work`
- **Authoring**: Prefer MCP **`create_event`** over hand-building with `create_note`

### 9. Root capture inbox (vault-root 01_seeds/) — no scope
- **Purpose**: Pre-scope captures awaiting triage (`type: capture`, not `type: seed`)
- **MCP tool**: **`capture`** (no scope parameter)
- **Schema**: `capture_type` (thought|post|excerpt), `source`, `captured`, `spark`, `status: inbox`

### 10. Blueprints (passion/07_blueprints/) — passion scope only
- **Purpose**: VPS infrastructure documentation
- **Naming**: `proj-*` → blueprint-project template; `tool-*` → blueprint-tool template (filename-prefix convention; no auto-template in MCP for other names)

## Key Principles

1. **Always preserve existing YAML frontmatter** when editing notes
2. **Use folder-appropriate templates** for new notes
3. **Maintain consistent metadata fields** for each note type
4. **Respect the PARA method structure** (Projects, Areas, Resources, Archives)
5. **Include agent_context field** for AI assistant guidance

## Template Usage Rules

- When creating new notes, detect the target folder and apply appropriate template
- When editing existing notes, preserve all existing frontmatter fields
- Add new frontmatter fields only if they match the note type's template
- Always include creation date and appropriate tags
- Link related notes using [[note-name]] syntax
"""
        raw = (note_type or "").strip().lower()
        aliases = {
            "daily_note": "daily",
            "dailies": "daily",
            "06_daily-notes": "daily",
            "projects": "project",
            "areas": "area",
            "seeds": "seed",
            "resources": "resource",
            "04_resources": "resource",
            "05_knowledge": "knowledge",
        }
        key = aliases.get(raw, raw if raw else None)
        if key not in {
            "daily",
            "project",
            "area",
            "seed",
            "resource",
            "knowledge",
        }:
            return full

        section_bounds = {
            "daily": ("### 1. Daily Notes (06_daily-notes/)", "### 2. Projects (02_projects/)"),
            "project": ("### 2. Projects (02_projects/)", "### 3. Areas (03_areas/)"),
            "area": ("### 3. Areas (03_areas/)", "### 4. Seeds (01_seeds/)"),
            "seed": ("### 4. Seeds (01_seeds/)", "### 5. Resources (04_resources/)"),
            "resource": ("### 5. Resources (04_resources/)", "### 6. Knowledge (05_knowledge/)"),
            "knowledge": ("### 6. Knowledge (05_knowledge/)", "## Key Principles"),
        }
        start_m, end_m = section_bounds[key]
        i = full.index(start_m)
        j = full.index(end_m)
        head = full[: full.index("## Note Types & Folders")] + "## Note Types & Folders\n\n"
        tail = full[full.index("## Key Principles") :]
        return head + full[i:j].rstrip() + "\n\n" + tail

    def _get_daily_note_template(self, date: str = None) -> str:
        """Daily note template prompt"""
        date_placeholder = date or "YYYY-MM-DD"
        return f"""# Daily Note Template

Use this template for daily notes in the `06_daily-notes/` folder (under the chosen workspace).

## File Structure
- **Filename**: `{date_placeholder}.md`
- **MCP path**: `06_daily-notes/{date_placeholder}.md` with `scope` set to the correct workspace (often `personal`).
- **On disk**: `<scope>/06_daily-notes/...` (scope is the workspace you pass, e.g. `personal`)

## Template:

```yaml
---
creation-date:
  "{date_placeholder}":
type: daily-note
focus: "7"
family_presence: "7"
learning_progress: "6"
well_being: "6"
tags:
  - journal/daily
---

# Daily Note for [Day], [Month] [Date] [Year]

## Morning Intentions
- [ ] 

## Key Events
- 

## Evening Reflection

### Grateful for:
- 

### What went well:
- 

### What could be improved:
- 

### Tomorrow's focus:
- 
```

## Field Explanations:
- **focus**: 1-10 scale for daily focus/productivity
- **family_presence**: 1-10 scale for family engagement
- **learning_progress**: 1-10 scale for learning/growth
- **well_being**: 1-10 scale for overall well-being
- **creation-date**: Nested date format for tracking

## Usage Notes:
- Always include the reflection sections
- Use the 1-10 rating scales consistently
- Add specific gratitude items and improvements
- Link to related projects/areas with [[note-name]]
"""

    def _get_project_note_template(self, project_name: str = None) -> str:
        """Project note template prompt"""
        name_placeholder = project_name or "[Project Name]"
        return f"""# Project Note Template

Use this template for project notes in the `02_projects/` folder inside a workspace.

## File Structure
- **Filename**: `{name_placeholder.lower().replace(' ', '-')}.md`
- **MCP path**: `02_projects/<filename>.md` plus required `scope` when the key has multiple workspaces.
- **On disk**: `<scope>/02_projects/...` (scope is the workspace you pass)

## Template:

```yaml
---
folder: 02_projects
type: project
created: YYYY-MM-DD
status: active
priority: medium
deadline: ""
spark_stage: project
project_goal: ""
success_criteria: ""
next_action: ""
related_areas: []
originated_from_seed: ""
tags:
  - project
  - [additional-tags]
agent_context: Actionable goal with specific deadline and measurable outcome
---

# {name_placeholder}

## Project Overview
**Goal**: [Clear, specific project outcome]
**Deadline**: [When this needs to be completed]
**Priority**: [High/Medium/Low based on urgency and importance]

## Success Criteria
- [ ] [Measurable outcome 1]
- [ ] [Measurable outcome 2]
- [ ] [Measurable outcome 3]

## Next Actions
- [ ] [Immediate next step]
- [ ] [Following action]

## Related Areas
- [[area-name]] - [How this project relates]

## Progress Log
### [Date] - [Status Update]
- [What was accomplished]

## Resources & Links
- [Relevant links, documents, references]
```

## Field Explanations:
- **status**: not_started, active, on_hold, completed, cancelled
- **priority**: high, medium, low
- **spark_stage**: Always "project" for this type
- **project_goal**: Clear, specific outcome statement
- **success_criteria**: Measurable definition of "done"
- **next_action**: Immediate actionable step
- **related_areas**: Links to ongoing areas this project supports

## Usage Notes:
- Projects have specific deadlines and outcomes
- Always include measurable success criteria
- Link to related areas of responsibility
- Track progress with dated updates
"""

    def _get_area_note_template(self, area_name: str = None) -> str:
        """Area note template prompt"""
        name_placeholder = area_name or "[Area Name]"
        return f"""# Area Note Template

Use this template for area notes in the `03_areas/` folder inside a workspace.

## File Structure
- **Filename**: `{name_placeholder.lower().replace(' ', '-')}.md`
- **MCP path**: `03_areas/<filename>.md` with appropriate `scope` (personal vs passion vs work).
- **On disk**: `<scope>/03_areas/...` (scope is the workspace you pass)

## Template:

```yaml
---
folder: 03_areas
type: area
created: YYYY-MM-DD
status: active
area_type: [personal/work/health/finance/etc]
spark_stage: area
responsibility_level: [high/medium/low]
review_frequency: [daily/weekly/monthly/quarterly]
related_projects: []
key_metrics: []
originated_from_seed: ""
tags:
  - area
  - [additional-tags]
agent_context: Ongoing life responsibility requiring continuous attention
---

# {name_placeholder}

## Area Overview
**Purpose**: [What this area of life is about]
**Responsibility Level**: [How important this is in your life]
**Review Frequency**: [How often you check in on this area]

## Standards & Goals
- [Standard 1: What "good" looks like in this area]
- [Standard 2: Ongoing expectation or goal]
- [Standard 3: Quality standard to maintain]

## Key Metrics
- [Metric 1]: [How you measure success]
- [Metric 2]: [Another way to track this area]

## Related Projects
- [[project-name]] - [How this project serves this area]

## Regular Activities
- [Recurring task or habit]
- [Another regular activity]

## Review Notes
### [Date] - [Review Type]
- [What's going well]
- [What needs attention]
- [Adjustments needed]

## Resources & References
- [Helpful links, books, contacts related to this area]
```

## Field Explanations:
- **area_type**: Category like personal, work, health, finance
- **responsibility_level**: high, medium, low - importance in your life
- **review_frequency**: How often you actively manage this area
- **key_metrics**: Ways you measure success in this area
- **related_projects**: Current projects that serve this area

## Usage Notes:
- Areas are ongoing responsibilities, not time-bound projects
- Focus on standards to maintain rather than specific outcomes
- Regular reviews help ensure areas don't slip
- Link projects that support this area of life
"""

    def _get_format_preservation_rules(self) -> str:
        """Format preservation guidelines"""
        return """# Format Preservation Rules

When editing existing notes via **MCP**, use **`update_note`** / **`append_note`** with the same **workspace-relative `path`** and **`scope`** you would use for **`read_note`**. Do not strip or rename YAML fields unless the user asked for a structural change.

When editing existing notes in this vault, follow these critical guidelines:

## YAML Frontmatter Preservation

### Rule 1: Never Remove Existing Fields
- **ALWAYS** preserve all existing YAML frontmatter fields
- Even if a field is empty (e.g., `deadline: ""`), keep it
- Maintain the exact field names and structure

### Rule 2: Respect Field Types
- **Dates**: Keep YYYY-MM-DD format
- **Lists**: Maintain array format with `[]` or `-` items
- **Strings**: Preserve quotes where they exist
- **Numbers**: Keep numeric values as numbers, not strings

### Rule 3: Add Fields Carefully
- Only add new fields that match the note type's template
- Check the note's `type` field to understand the expected schema
- Don't add arbitrary fields that break the template system

## Content Structure Preservation

### Rule 4: Maintain Heading Hierarchy
- Preserve existing heading levels (# ## ###)
- Don't change the main heading structure
- Add content within existing sections when possible

### Rule 5: Respect Note Type Conventions
- **Daily Notes**: Keep reflection sections and rating scales
- **Projects**: Preserve goal statements and success criteria structure
- **Areas**: Maintain standards and review sections
- **Seeds**: Keep simple, growth-oriented format

### Rule 6: Link Preservation
- Maintain existing `[[wikilinks]]` exactly as they are
- Don't break internal link references
- Use the same linking style when adding new links

## Editing Best Practices

### Before Editing:
1. **Read the entire note** to understand its current structure
2. **Check the YAML frontmatter** to identify the note type
3. **Identify the template pattern** being used

### During Editing:
1. **Work within existing sections** rather than restructuring
2. **Add content that fits the existing format**
3. **Preserve all metadata and structural elements**

### After Editing:
1. **Verify YAML frontmatter is intact**
2. **Check that links still work**
3. **Ensure the note still follows its template pattern**

## Error Prevention

### Common Mistakes to Avoid:
- ❌ Removing or changing YAML field names
- ❌ Breaking the date format in frontmatter
- ❌ Removing template sections (like "Success Criteria" in projects)
- ❌ Converting lists to paragraphs or vice versa
- ❌ Adding incompatible fields to note types

### Safe Editing Practices:
- ✅ Add content within existing sections
- ✅ Append to lists using the same format
- ✅ Update status fields with valid values
- ✅ Add new related links in appropriate sections
- ✅ Update progress logs with dated entries

## Template-Specific Guidelines

### For Daily Notes:
- Never change the rating scale format
- Keep the reflection structure intact
- Update ratings only with numbers 1-10

### For Projects:
- Always update `next_action` when progress is made
- Keep success criteria as checkboxes
- Maintain the progress log format

### For Areas:
- Preserve the standards format
- Keep review frequency consistent
- Maintain the metrics structure

Remember: **When in doubt, preserve the existing format** rather than risk breaking the template system.
"""

    def _get_meeting_prep_workflow(self, entity_name: Optional[str] = None) -> str:
        """Ties together get_dossier / build_context / create_event into one flow.

        These tools already exist and are individually documented in
        vault_mcp_agent_guide, but the guide only gives each one a one-line
        mention - this prompt is the missing "what do I call, in what order,
        for a whole meeting" walkthrough.
        """
        name = entity_name or "<entity name>"
        return f"""# Meeting Prep -> Logging Workflow (scope=work)

A work meeting has three phases as far as this MCP server is concerned:
**brief before**, **take the call**, **log after**. This prompt covers the
tool calls for the first and third phases - the middle one is you.

## 1. Before the meeting: brief yourself

Start with **`get_dossier`** - it wraps `resolve_entity` plus open questions
and recent cross-vault mentions in one call:

```
get_dossier(name="{name}", scope="work")
```

Add `since=<YYYY-MM-DD>` (e.g. the date of your last meeting with them) to
get a `changes_since` block - only what's new since then, so you don't
re-read the whole history every time.

If you need more than a dossier - e.g. you're prepping for a call that
touches several connected entities, or want a token-bounded brief you can
paste into a prompt - use **`build_context`** instead:

```
build_context(seed="{name}", scope="work", depth=1, token_budget=4000)
```

`build_context` expands typed neighbors (engaged_with/attended/attendees)
first, `related_to` second, mentions last, and returns a `source_manifest`
so you know exactly what it pulled in. Prefer `get_dossier` for a single
entity's brief; prefer `build_context` when the prep spans multiple
connected entities or you have a token budget to respect.

Only fall back to `read_note` on the entity's own card if the dossier's
`agent_context` and connections aren't enough - most meeting prep should
not need it.

## 2. During the meeting

(Nothing to call here - this is where you take notes.)

## 3. After the meeting: log it

Use **`create_event`**, not a hand-built note via `create_note` - it builds
the canonical filename, schema-valid frontmatter, and idempotently updates
the `## Events` back-ref on every entity the event touches:

```
create_event(
    event_type="discovery-call",   # controlled vocabulary - see vault_mcp_agent_guide
    customer="{name}",              # for customer-facing events
    participants=["<attendee 1>", "<attendee 2>"],
    event_date="<YYYY-MM-DD>",       # defaults to today if omitted
    agent_context="<one-line summary of what happened>",
    scope="work",
)
```

This makes the meeting a first-class graph node: `resolve_entity`,
`timeline`, and `last_touch` on `{name}` will pick it up immediately, and
`get_dossier(..., since=<event_date>)` next time will surface it in
`changes_since`.

## Quick reference

| When | Tool |
|------|------|
| Brief on one entity | `get_dossier` |
| Brief spanning multiple connected entities / token-bounded | `build_context` |
| Log what happened | `create_event` |
| "What's gone quiet" follow-up check | `last_touch` |
| Full interaction history | `timeline` |

For tool argument details and the entity graph model, see
**`vault_mcp_agent_guide`** (load once per session).
"""


# Global instance
obsidian_prompts = ObsidianPrompts()

