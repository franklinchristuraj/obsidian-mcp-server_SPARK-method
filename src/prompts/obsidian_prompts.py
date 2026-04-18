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
                    "Canonical guide: workspace folders (personal/passion/work), MCP tool choice, "
                    "scope parameter, paths vs resources—read this before other vault prompts."
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
| `work` | Employer projects, meetings, stakeholders, OKRs |

Each scope has its own `00_system/templates/`, `01_seeds/`, `02_projects/`, etc. Same relative path in two scopes is **two different notes**.

## 2. Start with `workspaces`

Call the **`workspaces`** tool once per session (or when unsure). It returns which scopes this **API key** may use. Do not assume access to all three.

## 3. Paths and `scope`

- **`path`** arguments are **relative to a workspace**, e.g. `06_daily-notes/2026-04-11.md`, `02_projects/My Project.md`.
- **Work meeting notes** use **`scope=work`** and paths under **`11_work-meeting-notes/`** (aligned with meeting templates in `template_utils`).
- **Never** put `personal/`, `passion/`, or `work/` as the first segment of `path`. Use the **`scope`** parameter instead.
- **Reads** (`search`, `list_notes`, `list_journal`, `read_note`, `note_exists`, `vault_structure`): optional `scope`. Omit it to search/list across **all scopes allowed for this key**; set it to narrow to one workspace.
- **Writes** (`create_note`, `update_note`, `append_note`, `delete_note`): if the key has **more than one** allowed scope, **`scope` is required**. If the key has exactly one scope, it is auto-selected.

## 4. Which tool when

| Goal | Tool | Notes |
|------|------|--------|
| See allowed scopes | `workspaces` | No arguments |
| Folder tree + counts | `vault_structure` | Optional `scope` |
| Browse files | `list_notes` | Optional `folder`, `scope`; optional mtime filters `modified_after`, `modified_before` (ISO `YYYY-MM-DD` or datetime, or `today` / `yesterday`), rolling `days` / `hours`, and `limit` (recent first) |
| Daily notes in date range | `list_journal` | `startDate`, `endDate`; optional `scope` |
| Find text in bodies | `search` | `keyword`; optional `folder`, `scope` |
| Read one file | `read_note` | `path`; optional `scope` (required if same path exists in two allowed scopes) |
| Check existence | `note_exists` | Same pattern as read |
| Create | `create_note` | `path`, `content`; `scope` if multi-scope key |
| Replace body | `update_note` | `scope` if multi-scope key |
| Append | `append_note` | `scope` if multi-scope key |
| Delete | `delete_note` | `scope` if multi-scope key |

Use only the tool names in the table above (legacy `obs_*` names are not registered).

## 5. MCP resources vs tools

- **`resources/list`** and **`resources/read`** use URIs like `obsidian://notes/personal/06_daily-notes/...` and show the **full physical vault tree**.
- They are **not** filtered by API-key workspace scope. If the connection is restricted (e.g. work-only key), **prefer `list_notes`, `read_note`, and `search`** with `scope` so the server enforces access.

## 6. Claude / Cursor skills (outside this server)

Align user-facing skills with: routing rules (which scope for which topic), new tool names, and “call `workspaces` first.” Work-only assistants should not describe personal/passion.

## 7. Template prompts

After this guide, use **`note_template_system`** and the type-specific prompts for YAML and section structure. Template paths on disk include the workspace (e.g. `personal/00_system/templates/...`); MCP **`create_note`** resolves templates using the **`scope`** you pass.

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
- **On disk**: `{scope}/06_daily-notes/...`

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
- **On disk**: `{scope}/02_projects/...`

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
- **On disk**: `{scope}/03_areas/...`

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


# Global instance
obsidian_prompts = ObsidianPrompts()

