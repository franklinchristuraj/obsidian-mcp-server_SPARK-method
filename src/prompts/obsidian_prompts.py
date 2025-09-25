"""
Obsidian MCP Prompts - Template and Format Instructions
Provides AI assistants with context about note templates and formatting rules
"""
from typing import List, Dict, Any
from ..types import MCPPrompt


class ObsidianPrompts:
    """
    MCP Prompts for Obsidian note templates and formatting guidelines
    """

    def get_prompts(self) -> List[MCPPrompt]:
        """Get all available prompts for note formatting and templates"""
        return [
            # Prompt 1: Note Template System Overview
            MCPPrompt(
                name="note_template_system",
                description="Learn about the Obsidian vault's note template system and formatting conventions",
                arguments=[
                    {
                        "name": "note_type",
                        "description": "Type of note to get template information for",
                        "required": False,
                    }
                ],
            ),
            # Prompt 2: Daily Note Template
            MCPPrompt(
                name="daily_note_template",
                description="Get the template and format for daily notes with proper YAML frontmatter",
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
                description="Get the template and format for project notes with proper metadata fields",
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
                description="Get the template and format for area notes (ongoing responsibilities)",
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
                description="Guidelines for preserving existing note formats when editing",
                arguments=[],
            ),
        ]

    async def get_prompt_content(
        self, prompt_name: str, arguments: Dict[str, Any] = None
    ) -> str:
        """Get the content for a specific prompt"""
        if arguments is None:
            arguments = {}

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

    def _get_template_system_prompt(self, note_type: str = None) -> str:
        """Template system overview prompt"""
        return """# Obsidian Vault Template System

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

    def _get_daily_note_template(self, date: str = None) -> str:
        """Daily note template prompt"""
        date_placeholder = date or "YYYY-MM-DD"
        return f"""# Daily Note Template

Use this template for daily notes in the `06_daily-notes/` folder:

## File Structure
- **Filename**: `{date_placeholder}.md`
- **Location**: `06_daily-notes/`

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

Use this template for project notes in the `02_projects/` folder:

## File Structure
- **Filename**: `{name_placeholder.lower().replace(' ', '-')}.md`
- **Location**: `02_projects/`

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

Use this template for area notes in the `03_areas/` folder:

## File Structure
- **Filename**: `{name_placeholder.lower().replace(' ', '-')}.md`
- **Location**: `03_areas/`

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

