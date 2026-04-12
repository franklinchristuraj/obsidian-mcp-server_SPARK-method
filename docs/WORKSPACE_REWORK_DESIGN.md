---
type: project
created: 2026-04-11
status: active
priority: high
spark_stage: project
project_goal: "Rework Ziksaka MCP server and Claude skills for workspace-aware routing across personal/passion/work folders"
success_criteria: "MCP enforces workspace scoping per API key. Claude skills match new structure. No dead weight in templates or tools. All 12 tools functional."
next_action: "Access VPS to audit Ziksaka codebase and implement workspace scoping middleware"
deadline: 2026-04-30
related_areas: []
originated_from_seed: ""
tags: [project, mcp, infrastructure]
agent_context: "Design doc for reworking Ziksaka MCP server to support workspace-aware routing. Covers access control, tool redesign (renamed from obs_ prefix), skill redesign, template audit, cleanup plan, and future knowledge graph extension points."
---

# MCP Workspace Rework — Design Document

## Problem Statement

Ziksaka MCP currently serves the entire vault as a flat namespace. All tools operate on all files. There's no way to scope an API key to a specific workspace. The Claude skill still describes the old flat SPARK structure. Two tools are broken (search, execute_command). Tool names carry a redundant `obs_` prefix. Root-level legacy folders add noise.

---

## Target Architecture

### One vault, three workspaces, scoped access

```
franklin-vault/
├── personal/     ← daily journal, finance, family, people, trips
├── passion/      ← AI research, side projects, blueprints, content
├── work/         ← Make/Celonis projects, meetings, stakeholders
```

Legacy folders (`00_system/`, `01_seeds/`, `z_archive/`, `CLAUDE.md/`) to be archived and removed.

### Access control model

Think of it like apartment building keycards — same building, different access levels.

| Consumer                    | Key Type | Scopes                  | Use Case                                              |
| --------------------------- | -------- | ----------------------- | ----------------------------------------------------- |
| Personal Claude (claude.ai) | personal | personal, passion       | Daily journal, life planning, side projects, research |
| Work Claude (claude.ai)     | work     | work                    | Meetings, stakeholders, work projects                 |
| Franklin (admin)            | admin    | personal, passion, work | Cross-workspace operations, maintenance               |
| n8n research agent          | custom   | passion                 | Forward Intelligence Radar deposits                   |
| n8n slack triage agent      | custom   | work                    | Slack summaries → work vault                          |
| Make workflow               | custom   | passion                 | Content pipeline operations                           |
| LangGraph agent             | custom   | work OR passion         | Depends on use case                                   |

### Key-to-workspace mapping config

Stored in `workspace_keys.json`:

```json
{
  "keys": {
    "sk_admin_xxxxx": {
      "name": "Franklin Admin",
      "scopes": ["personal", "passion", "work"],
      "role": "admin"
    },
    "sk_personal_xxxxx": {
      "name": "Personal Claude",
      "scopes": ["personal", "passion"],
      "role": "user"
    },
    "sk_work_xxxxx": {
      "name": "Work Claude",
      "scopes": ["work"],
      "role": "user"
    },
    "sk_n8n_research_xxxxx": {
      "name": "n8n Research Agent",
      "scopes": ["passion"],
      "role": "agent"
    },
    "sk_n8n_slack_xxxxx": {
      "name": "n8n Slack Triage",
      "scopes": ["work"],
      "role": "agent"
    }
  }
}
```

### Workspace scoping — connection-level enforcement

The API key determines scope. Tools have the same interface but the server silently:

1. **Prepends workspace prefix** to all paths
2. **Restricts listing/search** to allowed scopes only
3. **Blocks writes** to unauthorized scopes
4. **Returns clean paths** without the workspace prefix (agents don't know other scopes exist)

---

## Scope Parameter Behavior

The `scope` parameter is **optional on read operations** (narrows results) and **required on write operations for multi-scope keys** (tells server where to put the note).

### Read operations (search, list_notes, list_journal, read_note, note_exists)

| Caller has... | `scope` omitted | `scope: "work"` specified |
|---------------|-----------------|---------------------------|
| 1 scope (e.g., work key) | Auto-scoped to that scope | Redundant but accepted |
| 2+ scopes (e.g., personal key) | Searches ALL allowed scopes | Searches only specified scope |
| Admin (3 scopes) | Searches ALL scopes | Searches only specified scope |

Results always include a `scope` field so the caller knows which workspace each result belongs to.

### Write operations (create_note, update_note, append_note, delete_note)

| Caller has... | `scope` omitted | `scope` specified |
|---------------|-----------------|-------------------|
| 1 scope | Auto-selected (silent) | Validated, accepted |
| 2+ scopes | **ERROR** — "specify scope" | Validated, accepted |
| Admin | **ERROR** — "specify scope" | Validated, accepted |

### Example flows

**Personal Claude creating a daily note:**
```
create_note(path="06_daily-notes/2026-04-11.md", scope="personal", content="...")
→ Server creates at: personal/06_daily-notes/2026-04-11.md
→ Returns: { path: "06_daily-notes/2026-04-11.md", scope: "personal" }
```

**Work agent creating a meeting note (single-scope key, auto-selected):**
```
create_note(path="11_meeting-notes/2026-04-11-standup.md", content="...")
→ Server auto-selects scope "work"
→ Creates at: work/11_meeting-notes/2026-04-11-standup.md
→ Returns: { path: "11_meeting-notes/2026-04-11-standup.md", scope: "work" }
```

**Personal Claude searching across scopes:**
```
search(keyword="stakeholders")
→ Returns results from personal/ AND passion/ (both allowed scopes)
→ Each result tagged with scope: "personal" or scope: "passion"
```

**Personal Claude narrowing search to one scope:**
```
search(keyword="architecture", scope="passion")
→ Returns results from passion/ only
```

---

## Tool Redesign

### Tool Audit Results (2026-04-11)

| Old Name | Status | Issue |
|----------|--------|-------|
| ping | WORKS | No issues |
| obs_get_vault_structure | PARTIAL | Note counts wrong — doesn't recurse subfolders |
| obs_list_notes | WORKS | No issues |
| obs_list_daily_notes | PARTIAL | Returns duplicates across workspaces, no scope indicator |
| obs_read_note | WORKS | No issues |
| obs_create_note | WORKS | Template auto-apply and manual content both work |
| obs_update_note | WORKS | No issues |
| obs_append_note | WORKS | No issues |
| obs_check_note_exists | WORKS | No issues |
| obs_delete_note | WORKS | No issues |
| obs_keyword_search | WORKS | Functional search |
| obs_search_notes | **BROKEN** | Fails with empty error — dead tool |
| obs_execute_command | **BROKEN** | Command endpoint not found — dead tool |

### Final Tool Set (12 tools)

Renamed from `obs_` prefix (redundant since server only serves Obsidian). Dropped broken tools. Added workspace discovery. Old `obs_*` names kept as aliases during transition.

| # | New Name | Old Name (alias) | Parameters | Notes |
|---|----------|------------------|------------|-------|
| 1 | **ping** | ping | — | Connectivity test |
| 2 | **workspaces** | *(new)* | — | Returns scopes available to current key |
| 3 | **vault_structure** | obs_get_vault_structure | `scope?` | **FIX:** recursive note counting. Filtered by allowed scopes |
| 4 | **list_notes** | obs_list_notes | `folder?`, `scope?` | Scoped to allowed workspaces |
| 5 | **list_journal** | obs_list_daily_notes | `startDate`, `endDate`, `scope?` | **FIX:** deduplicate, add scope to results |
| 6 | **search** | obs_keyword_search | `keyword`, `folder?`, `scope?`, `limit?` | Only search tool needed. Scoped |
| 7 | **read_note** | obs_read_note | `path`, `scope?` | Validates path within allowed scope |
| 8 | **create_note** | obs_create_note | `path`, `content`, `scope` (req for multi-scope), `use_template?`, `template_vars?` | Prepends scope prefix |
| 9 | **update_note** | obs_update_note | `path`, `content`, `scope?`, `preserve_format?` | Validates scope access |
| 10 | **append_note** | obs_append_note | `path`, `content`, `scope?` | Validates scope access |
| 11 | **note_exists** | obs_check_note_exists | `path`, `scope?` | Boolean check within scope |
| 12 | **delete_note** | obs_delete_note | `path`, `scope?` | Validates scope access |

### Dropped tools

| Tool | Reason |
|------|--------|
| obs_search_notes | Broken. Redundant with `search` (keyword_search) |
| obs_execute_command | Broken. Security risk for agents. Obsidian commands affect the whole app, not specific scopes |

### Potential future tool

| Tool | Purpose | When to add |
|------|---------|-------------|
| **promote_note** | Cross-scope note copy (e.g., work seed → passion seed). Strips specified fields/patterns. Admin-only | When cross-scope workflow is needed regularly |

---

## Future Extension: Knowledge Graphs & Semantic Search

Each scope will eventually get its own knowledge graph for semantic search and relationship mapping. The architecture is designed to support this cleanly:

### How it fits

```
franklin-vault/
├── personal/     → personal knowledge graph (Weaviate collection)
├── passion/      → passion knowledge graph (Weaviate collection)
├── work/         → work knowledge graph (Weaviate collection)
```

The `scope` parameter routes to the right graph, same as it routes to the right folder. A multi-scope search would query multiple Weaviate collections and merge results.

### Future tools to add

| Tool | Purpose |
|------|---------|
| **semantic_search** | Vector similarity search across notes within scope. Returns ranked results by relevance |
| **related_notes** | Given a note path, find semantically related notes within scope (graph traversal) |
| **graph_status** | Returns embedding stats per scope (indexed notes count, last sync, coverage gaps) |

### Infrastructure needed

- Weaviate collections: one per scope (e.g., `personal_notes`, `passion_notes`, `work_notes`)
- Embedding pipeline: n8n workflow that watches for note changes → generates embeddings → upserts to Weaviate
- Scope isolation: work embeddings never mixed with personal/passion in the same collection

### Design principle

The keyword `search` tool stays as the fast, exact-match tool. `semantic_search` becomes the fuzzy, meaning-based tool. Both respect scope. Agents choose based on whether they're looking for a specific term or a concept.

---

## Claude Skill Redesign

### Skill 1: franklin-obsidian-vault (Master — for Personal Claude)

Covers all three workspaces. Loaded by personal Claude app.

**Key changes from current skill:**
- Describes the three-workspace model with scope parameter
- References workspace-specific README files for context
- Includes workspace routing guidance (when to use personal vs passion vs work)
- Points to workspace-specific templates
- Removes all references to old flat folder structure
- Uses new tool names (no `obs_` prefix)

**Workspace routing guidance:**

```
When the user asks about daily journal, family, finances, trips, health, relationship, dogs, personal planning:
  → scope: personal

When the user asks about AI research, side projects, blueprints, VPS, content, YouTube, LinkedIn, learning, courses, Frank About AI:
  → scope: passion

When the user asks about Make, Celonis, stakeholders, OKRs, work meetings, work projects, Slack, VE role:
  → scope: work (note: personal Claude may not have access — inform user)

When ambiguous or cross-cutting:
  → omit scope to search across all allowed workspaces, then narrow
```

**Reference files to update:**

| File | Changes |
|------|---------|
| `references/spark-templates.md` | Split into per-workspace sections |
| `references/personal-context.md` | Update folder paths, confirm current |
| `references/work-context.md` | Update role to VE, new manager Carlos, new reporting line |
| `references/passion-context.md` | Update folder paths, confirm current |

### Skill 2: franklin-work-vault (Work — for Work Claude)

Covers work scope only. Loaded by work Claude app.

**Scope:** work/ folder only. Task system, meeting notes, stakeholders, projects, OKRs, Slack reports.

**Does NOT reference:** personal or passion workspaces. No awareness of them.

**Key content:**
- Work role context (VE role, Carlos as manager, Natalia as VP Revenue)
- Stakeholder map
- Task conventions (inline Dataview format)
- Meeting note templates
- Work-specific folder map
- Uses new tool names (no `obs_` prefix)

---

## Template Audit & Cleanup

### Root-level legacy (TO DELETE)

33 notes in `00_system/` superseded by workspace-specific copies. Also 2 orphans in `01_seeds/`, 2 in `z_archive/`, and empty `CLAUDE.md/` folder.

**Action plan:**
1. Check if `01_seeds/` root notes are already migrated → if yes, delete
2. Move `z_archive/` root notes to appropriate workspace archive → then delete
3. Delete all root `00_system/` content (templates are duplicates, agent-memory already copied, system docs already in workspace READMEs)
4. Delete empty `CLAUDE.md/` folder

### Per-workspace template status

**Personal (8 templates) — CLEAN:**
seed.md, area.md, project.md, daily-journal.md, person.md, context.md, finance-overview.md, monthly-finance.md

**Passion (8 templates) — CLEAN:**
seed.md, project.md, area.md, resource.md, knowledge.md, daily-build-log.md, blueprint-tool.md, blueprint-project.md

**Work (7 templates) — NEEDS UPDATE:**
seed.md, project.md, area.md, resource.md, meeting-notes.md, daily-standup.md, task-conventions.md
- [ ] Update role references: Samurai → VE
- [ ] Update manager references: Sara → Carlos
- [ ] Update reporting line references

### Template auto-detection in MCP

The `create_note` tool's `use_template` logic needs updating for workspace-prefixed paths:

| Agent calls | Server resolves template from |
|-------------|-------------------------------|
| `create_note(path="01_seeds/x.md", scope="personal")` | `personal/00_system/templates/seed.md` |
| `create_note(path="01_seeds/x.md", scope="passion")` | `passion/00_system/templates/seed.md` |
| `create_note(path="01_seeds/x.md", scope="work")` | `work/00_system/templates/seed.md` |
| `create_note(path="11_meeting-notes/x.md", scope="work")` | `work/00_system/templates/meeting-notes.md` |

Each workspace has its own templates folder, so the same folder name maps to different templates depending on scope. This is the correct behavior — a personal seed has a lighter template than a passion seed.

---

## Implementation Checklist

### Phase 1: Vault cleanup
- [ ] Verify `01_seeds/` root notes are migrated, then delete
- [ ] Move `z_archive/` root notes to workspace archives, then delete
- [ ] Delete root `00_system/` (all 33 notes)
- [ ] Delete empty `CLAUDE.md/` folder
- [ ] Verify no workspace notes have broken links to deleted root files

### Phase 2: MCP server rework
- [ ] Audit Ziksaka codebase on VPS (understand current architecture)
- [ ] Create `workspace_keys.json` with key-to-scope mappings
- [ ] Create `src/scope.py` with `resolve_scoped_path()` function
- [ ] Update `src/auth.py` to load keys and attach scopes to request
- [ ] Add scope middleware (path prepending, access validation)
- [ ] Add new tool names alongside old `obs_*` aliases (parallel deployment)
- [ ] Remove broken tools (obs_search_notes, obs_execute_command)
- [ ] Add `workspaces` tool
- [ ] Add `scope` parameter to all tools (optional on reads, required on multi-scope writes)
- [ ] Fix `vault_structure` recursive note counting
- [ ] Fix `list_journal` deduplication and scope tagging
- [ ] Update template auto-detection for scope-prefixed paths
- [ ] Add `scope` field to all response metadata
- [ ] Test: work key cannot read personal/ files
- [ ] Test: personal key can read personal/ + passion/ but not work/
- [ ] Test: admin key reads everything
- [ ] Test: multi-scope search returns scope-tagged results
- [ ] Test: single-scope key auto-selects scope on writes

### Phase 3: Claude skill updates
- [ ] Rewrite `franklin-obsidian-vault` SKILL.md for workspace model with new tool names
- [ ] Create `franklin-work-vault` SKILL.md for work Claude
- [ ] Update `references/work-context.md` (VE role, Carlos, Natalia)
- [ ] Update `references/personal-context.md` (verify current)
- [ ] Update `references/passion-context.md` (verify current)
- [ ] Update `references/spark-templates.md` (per-workspace sections)

### Phase 4: Key provisioning
- [ ] Create admin key (all scopes)
- [ ] Create personal key (personal + passion)
- [ ] Create work key (work only)
- [ ] Create n8n research agent key (passion only)
- [ ] Create n8n slack agent key (work only)
- [ ] Document key management process
- [ ] Update Claude desktop app MCP connector configs

### Phase 5: Future — Knowledge graphs (not now)
- [ ] Set up Weaviate collections per scope
- [ ] Build embedding pipeline (n8n → Weaviate)
- [ ] Add semantic_search tool
- [ ] Add related_notes tool
- [ ] Add graph_status tool

---

## Resolved Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Architecture | Single vault, three workspace folders | Simpler than multi-vault, keeps REST API |
| API approach | Keep Obsidian REST API | Working today, no infra changes needed |
| Key storage | JSON config file (`workspace_keys.json`) | Simple, ~5 keys, easy to edit |
| Tool renaming | Parallel deployment — keep `obs_*` aliases | Safe migration, remove aliases after 30 days |
| Workspace enforcement | Connection-level (Approach B) | More secure, agents can't accidentally cross boundaries |
| Tool naming | Drop `obs_` prefix for new names | Server only serves Obsidian, prefix is redundant |
| Broken search tool | Drop, keep keyword_search as `search` | obs_search_notes is dead, keyword_search covers the need |
| obs_execute_command | Drop | Broken, security risk, not workspace-scoped |
| append_note | Keep | Valuable for adding insights to long notes without rewriting |
| Scope parameter name | `scope` | Short, clear, agent-token-efficient |
| Cross-workspace key | Yes (admin role) | Needed for maintenance and future orchestrator agent |
| Skill architecture | 1 master + 1 work-only | Matches the two Claude app instances |
| Default search behavior (multi-scope) | Search all allowed scopes | User can narrow with scope param when needed |
| Error messages | Generic "not found" | Don't leak scope/path info to unauthorized keys |
| Knowledge graph timeline | Future (Phase 5) | Architecture supports it, but not needed now |

---

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `workspace_keys.json` | **NEW** | Key-to-scope mapping config |
| `src/scope.py` | **NEW** | `resolve_scoped_path()`, scope validation logic |
| `src/auth.py` | **MODIFY** | Load workspace keys, attach scopes to request context |
| `src/tools/obsidian_tools.py` | **MODIFY** | Add scope param to all tools, add aliases, use scoped paths |
| `src/utils/template_utils.py` | **MODIFY** | Scope-aware template path resolution |
| `src/mcp_server.py` | **MODIFY** | Add `workspaces` tool, remove broken tools from registry |

---

## Core Implementation: Scope Resolution

The entire scope system centers on one function:

```python
def resolve_scoped_path(
    user_path: str,           # What agent sends: "01_seeds/idea.md"
    scope: str,               # Determined from key or param: "personal"
    allowed_scopes: list[str] # From key config: ["personal", "passion"]
) -> str:
    """
    Returns: "personal/01_seeds/idea.md"
    Raises: PermissionError if scope not in allowed_scopes
    Raises: ValueError if path contains traversal attempts
    """
    if scope not in allowed_scopes:
        raise PermissionError(f"Access denied to scope: {scope}")

    # Prevent path traversal
    if ".." in user_path or user_path.startswith("/"):
        raise ValueError("Invalid path")

    return f"{scope}/{user_path}"
```

Every tool calls this before any filesystem/API operation.
```

---
