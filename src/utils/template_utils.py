"""
Template utilities for note creation and format preservation
"""
import re
import yaml
from datetime import datetime
from typing import Dict, Any, Optional, Tuple


class TemplateDetector:
    """Detects and applies appropriate templates based on folder and note type"""

    def __init__(self):
        # Folder to note type mapping (canonical folder names)
        self.folder_templates = {
            "06_daily-notes": "daily-note",
            "02_projects": "project",
            "03_areas": "area",
            "01_seeds": "seed",
            "04_resources": "resource",
            "05_knowledge": "knowledge",
            "11_work-meeting-notes": "meeting-note",
        }

        # Vault-based template file paths (SPARK structure)
        # Maps folder to template file path in vault
        self.vault_templates = {
            "11_work-meeting-notes": "00_system/templates/meeting-notes_template.md",
            "01_seeds": "00_system/templates/seed_template.md",
            "02_projects": "00_system/templates/project_template.md",
            "03_areas": "00_system/templates/area_template.md",
            "04_resources": "00_system/templates/resource_template.md",
            "05_knowledge": "00_system/templates/knowledge_template.md",
            "06_daily-notes": "00_system/templates/daily-note_template.md",
        }

        # Folder aliases - map alternative folder names to canonical names
        # This allows flexible folder naming while still applying the right templates
        self.folder_aliases = {
            # Meeting notes variations
            "work-meeting-notes": "11_work-meeting-notes",
            "work meeting notes": "11_work-meeting-notes",
            "meetings": "11_work-meeting-notes",
            "meeting-notes": "11_work-meeting-notes",
            "work meetings": "11_work-meeting-notes",

            # Daily notes variations
            "daily-notes": "06_daily-notes",
            "daily notes": "06_daily-notes",
            "journal": "06_daily-notes",
            "dailies": "06_daily-notes",

            # Projects variations
            "projects": "02_projects",
            "project": "02_projects",

            # Areas variations
            "areas": "03_areas",
            "area": "03_areas",

            # Seeds variations
            "seeds": "01_seeds",
            "seed": "01_seeds",
            "ideas": "01_seeds",

            # Resources variations
            "resources": "04_resources",
            "resource": "04_resources",

            # Knowledge variations
            "knowledge": "05_knowledge",
            "kb": "05_knowledge",
            "knowledge-base": "05_knowledge",
        }

    def normalize_folder_path(self, path: str) -> str:
        """
        Normalize a folder path to its canonical form using aliases
        Returns the original path if no alias matches
        """
        if not path:
            return path

        # Extract the first folder component
        parts = path.split("/")
        first_folder = parts[0].strip()

        # Check for exact match first (case-sensitive)
        if first_folder in self.folder_templates:
            return path

        # Check aliases (case-insensitive)
        first_folder_lower = first_folder.lower()
        if first_folder_lower in self.folder_aliases:
            canonical = self.folder_aliases[first_folder_lower]
            # Replace first folder with canonical name
            parts[0] = canonical
            return "/".join(parts)

        # Return original path if no match
        return path

    def detect_note_type_from_path(self, path: str) -> Optional[str]:
        """Detect note type from file path"""
        # Normalize the path first to handle aliases
        normalized_path = self.normalize_folder_path(path)

        for folder, note_type in self.folder_templates.items():
            if normalized_path.startswith(folder + "/") or normalized_path.startswith(folder):
                return note_type
        return None

    def get_template_path_for_folder(self, path: str) -> Optional[str]:
        """Get vault template file path for a given note path"""
        # Normalize the path first to handle aliases
        normalized_path = self.normalize_folder_path(path)

        for folder, template_path in self.vault_templates.items():
            if normalized_path.startswith(folder + "/") or normalized_path.startswith(folder):
                return template_path
        return None

    def apply_template(self, template_content: str, **variables) -> str:
        """
        Apply variable substitution to template content
        Simple .replace() for {{variable}} syntax

        Args:
            template_content: The template file content from vault
            **variables: Variable name-value pairs for substitution

        Returns:
            Template content with variables substituted
        """
        result = template_content
        for key, value in variables.items():
            # Replace {{key}} with value
            result = result.replace(f"{{{{{key}}}}}", str(value))
        return result

    def extract_frontmatter(self, content: str) -> Tuple[Dict[str, Any], str]:
        """Extract YAML frontmatter and content body"""
        if not content.startswith("---"):
            return {}, content

        try:
            # Find the closing ---
            end_marker = content.find("---", 3)
            if end_marker == -1:
                return {}, content

            frontmatter_text = content[3:end_marker].strip()
            body = content[end_marker + 3 :].strip()

            frontmatter = yaml.safe_load(frontmatter_text) if frontmatter_text else {}
            return frontmatter or {}, body

        except yaml.YAMLError:
            return {}, content

    def build_content_with_frontmatter(
        self, frontmatter: Dict[str, Any], body: str
    ) -> str:
        """Combine frontmatter and body into complete note content"""
        if not frontmatter:
            return body

        yaml_content = yaml.dump(frontmatter, default_flow_style=False, sort_keys=False)
        return f"---\n{yaml_content}---\n\n{body}"

    def get_default_frontmatter(self, note_type: str, path: str) -> Dict[str, Any]:
        """Get default frontmatter for a note type"""
        today = datetime.now().strftime("%Y-%m-%d")

        if note_type == "daily-note":
            return {
                "creation-date": {today: None},
                "type": "daily-note",
                "focus": "7",
                "family_presence": "7",
                "learning_progress": "6",
                "well_being": "6",
                "tags": ["journal/daily"],
            }
        elif note_type == "project":
            return {
                "folder": "02_projects",
                "type": "project",
                "created": today,
                "status": "active",
                "priority": "medium",
                "deadline": "",
                "spark_stage": "project",
                "project_goal": "",
                "success_criteria": "",
                "next_action": "",
                "related_areas": [],
                "originated_from_seed": "",
                "tags": ["project"],
                "agent_context": "Actionable goal with specific deadline and measurable outcome",
            }
        elif note_type == "area":
            return {
                "folder": "03_areas",
                "type": "area",
                "created": today,
                "status": "active",
                "area_type": "",
                "spark_stage": "area",
                "responsibility_level": "medium",
                "review_frequency": "monthly",
                "related_projects": [],
                "key_metrics": [],
                "originated_from_seed": "",
                "tags": ["area"],
                "agent_context": "Ongoing life responsibility requiring continuous attention",
            }
        elif note_type == "seed":
            return {
                "folder": "01_seeds",
                "type": "seed",
                "created": today,
                "status": "not_started",
                "tags": ["seed"],
            }
        elif note_type == "resource":
            return {
                "folder": "04_resources",
                "type": "resource",
                "created": today,
                "source": "",
                "tags": ["resource"],
            }
        elif note_type == "knowledge":
            return {
                "folder": "05_knowledge",
                "type": "knowledge",
                "created": today,
                "tags": ["knowledge"],
            }
        elif note_type == "meeting-note":
            return {
                "folder": "11_work-meeting-notes",
                "type": "meeting-note",
                "date": today,
                "created": today,
                "meeting_type": "",
                "attendees": [],
                "project": "",
                "status": "scheduled",
                "tags": ["meeting", "work"],
            }
        else:
            return {"created": today, "type": "note"}

    def get_default_body_template(self, note_type: str, note_name: str = "") -> str:
        """Get default body template for a note type"""
        if note_type == "daily-note":
            date_obj = datetime.now()
            formatted_date = date_obj.strftime("%A, %B %d, %Y")
            return f"""# Daily Note for {formatted_date}

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
- """

        elif note_type == "project":
            return f"""# {note_name or "Project Name"}

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
### {datetime.now().strftime("%Y-%m-%d")} - Project Started
- [Initial notes and planning]

## Resources & Links
- [Relevant links, documents, references]"""

        elif note_type == "area":
            return f"""# {note_name or "Area Name"}

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
### {datetime.now().strftime("%Y-%m-%d")} - Area Setup
- [Initial thoughts and planning]

## Resources & References
- [Helpful links, books, contacts related to this area]"""

        elif note_type == "seed":
            return f"""# {note_name or "Seed Idea"}

## Initial Thoughts
[Capture the raw idea or concept]

## Potential Development
- [How this could grow into a project]
- [What areas of life this might impact]

## Next Steps
- [ ] [First exploration step]
- [ ] [Research or validation needed]

## Related Notes
- [[related-note]] - [Connection]"""

        elif note_type == "resource":
            return f"""# {note_name or "Resource Title"}

## Source Information
**URL**: [Link to original source]
**Author**: [Author or creator]
**Type**: [Book/Article/Video/Course/etc]
**Date Accessed**: {datetime.now().strftime("%Y-%m-%d")}

## Key Insights
- [Main takeaway 1]
- [Main takeaway 2] 
- [Main takeaway 3]

## Practical Applications
- [How to apply this information]
- [Action items or next steps]

## Related Resources
- [[other-resource]] - [Connection]"""

        elif note_type == "knowledge":
            return f"""# {note_name or "Knowledge Topic"}

## Overview
[Brief description of the concept or topic]

## Key Concepts
- **Concept 1**: [Definition or explanation]
- **Concept 2**: [Definition or explanation]

## Examples
- [Real-world example 1]
- [Real-world example 2]

## Applications
- [How to use this knowledge]
- [When this concept applies]

## Related Knowledge
- [[related-concept]] - [Connection]"""

        elif note_type == "meeting-note":
            date_obj = datetime.now()
            formatted_date = date_obj.strftime("%Y-%m-%d")
            formatted_time = date_obj.strftime("%H:%M")
            return f"""# {note_name or "Meeting Notes"}

## Meeting Details
**Date**: {formatted_date}
**Time**: {formatted_time}
**Type**: [Team Meeting / 1:1 / Client Call / Review / etc.]
**Attendees**:
- [Name 1]
- [Name 2]

## Agenda
1. [Topic 1]
2. [Topic 2]
3. [Topic 3]

## Discussion Points

### [Topic 1]
- [Key point discussed]
- [Decision made or action needed]

### [Topic 2]
- [Key point discussed]
- [Decision made or action needed]

## Action Items
- [ ] [Action 1] - @[Person] - Due: [Date]
- [ ] [Action 2] - @[Person] - Due: [Date]
- [ ] [Action 3] - @[Person] - Due: [Date]

## Decisions Made
- [Decision 1 and rationale]
- [Decision 2 and rationale]

## Follow-up
- [Next meeting date/time if applicable]
- [Items to revisit]
- [People to follow up with]

## Notes & Observations
[Additional context, observations, or notes from the meeting]

## Related Links
- [[related-project]] - [Connection]
- [[related-area]] - [Connection]"""

        else:
            return f"""# {note_name or "Note Title"}

[Note content goes here]"""

    def preserve_existing_structure(
        self, existing_content: str, new_content: str, note_type: str
    ) -> str:
        """Preserve existing note structure when updating"""
        existing_frontmatter, existing_body = self.extract_frontmatter(existing_content)
        new_frontmatter, new_body = self.extract_frontmatter(new_content)

        # Merge frontmatter - preserve existing fields, add new ones carefully
        merged_frontmatter = existing_frontmatter.copy()

        # Only add new fields that are appropriate for the note type
        for key, value in new_frontmatter.items():
            if key not in merged_frontmatter or not merged_frontmatter[key]:
                merged_frontmatter[key] = value

        # Use new body content but preserve structure if minimal changes
        final_body = new_body if new_body.strip() else existing_body

        return self.build_content_with_frontmatter(merged_frontmatter, final_body)

    def should_apply_template(self, path: str, existing_content: str = "") -> bool:
        """Determine if template should be applied to a note"""
        # Don't apply template if note already has substantial content
        if existing_content.strip():
            frontmatter, body = self.extract_frontmatter(existing_content)
            # If body has more than just headings, don't override
            body_lines = [
                line
                for line in body.split("\n")
                if line.strip() and not line.startswith("#")
            ]
            if len(body_lines) > 3:
                return False

        # Apply template for new notes in template folders
        note_type = self.detect_note_type_from_path(path)
        return note_type is not None

    def build_meeting_note_from_data(
        self,
        title: str = "",
        date: str = "",
        time: str = "",
        meeting_type: str = "",
        attendees: list = None,
        agenda: list = None,
        discussion: str = "",
        discussion_points: list = None,
        action_items: list = None,
        decisions: list = None,
        follow_up: str = "",
        notes: str = "",
        related_links: list = None,
        **extra_vars
    ) -> Tuple[Dict[str, Any], str]:
        """
        Build a meeting note from structured data, including only sections with content.
        Returns (frontmatter_dict, body_string)

        Args:
            title: Meeting title
            date: Meeting date (YYYY-MM-DD format)
            time: Meeting time
            meeting_type: Type of meeting (standup, planning, review, etc.)
            attendees: List of attendee names or dicts with name/role
            agenda: List of agenda items
            discussion: Raw discussion transcript or notes
            discussion_points: List of discussion point dicts {topic, points}
            action_items: List of action item dicts {task, assignee, due_date}
            decisions: List of decisions made
            follow_up: Follow-up notes
            notes: Additional notes and observations
            related_links: List of related wiki links
        """
        # Build frontmatter
        today = datetime.now().strftime("%Y-%m-%d")
        frontmatter = {
            "folder": "11_work-meeting-notes",
            "type": "meeting-note",
            "date": date or today,
            "created": today,
        }

        if meeting_type:
            frontmatter["meeting_type"] = meeting_type
        if attendees:
            frontmatter["attendees"] = attendees
        frontmatter["tags"] = ["meeting", "work"]

        # Build body with only sections that have content
        body_parts = []

        # Title
        note_title = title or "Meeting Notes"
        body_parts.append(f"# {note_title}\n")

        # Meeting Details section - only if we have details
        details_parts = []
        if date:
            details_parts.append(f"**Date**: {date}")
        if time:
            details_parts.append(f"**Time**: {time}")
        if meeting_type:
            details_parts.append(f"**Type**: {meeting_type}")

        if attendees:
            details_parts.append("**Attendees**:")
            for attendee in attendees:
                if isinstance(attendee, dict):
                    name = attendee.get("name", "")
                    role = attendee.get("role", "")
                    details_parts.append(f"- {name}" + (f" ({role})" if role else ""))
                else:
                    details_parts.append(f"- {attendee}")

        if details_parts:
            body_parts.append("## Meeting Details")
            body_parts.append("\n".join(details_parts))
            body_parts.append("")

        # Agenda section - only if provided
        if agenda:
            body_parts.append("## Agenda")
            for i, item in enumerate(agenda, 1):
                body_parts.append(f"{i}. {item}")
            body_parts.append("")

        # Discussion section
        if discussion:
            body_parts.append("## Discussion")
            body_parts.append(discussion)
            body_parts.append("")
        elif discussion_points:
            body_parts.append("## Discussion Points")
            body_parts.append("")
            for point in discussion_points:
                if isinstance(point, dict):
                    topic = point.get("topic", "Topic")
                    points = point.get("points", [])
                    body_parts.append(f"### {topic}")
                    for p in points:
                        body_parts.append(f"- {p}")
                else:
                    body_parts.append(f"- {point}")
                body_parts.append("")

        # Action Items section - only if provided
        if action_items:
            body_parts.append("## Action Items")
            for item in action_items:
                if isinstance(item, dict):
                    task = item.get("task", item.get("action", ""))
                    assignee = item.get("assignee", item.get("person", ""))
                    due_date = item.get("due_date", item.get("due", ""))

                    action_text = f"- [ ] {task}"
                    if assignee:
                        action_text += f" - @{assignee}"
                    if due_date:
                        action_text += f" - Due: {due_date}"
                    body_parts.append(action_text)
                else:
                    body_parts.append(f"- [ ] {item}")
            body_parts.append("")

        # Decisions section - only if provided
        if decisions:
            body_parts.append("## Decisions Made")
            for decision in decisions:
                if isinstance(decision, dict):
                    dec = decision.get("decision", "")
                    rationale = decision.get("rationale", "")
                    body_parts.append(f"- {dec}" + (f" - {rationale}" if rationale else ""))
                else:
                    body_parts.append(f"- {decision}")
            body_parts.append("")

        # Follow-up section - only if provided
        if follow_up:
            body_parts.append("## Follow-up")
            body_parts.append(follow_up)
            body_parts.append("")

        # Notes section - only if provided
        if notes:
            body_parts.append("## Notes & Observations")
            body_parts.append(notes)
            body_parts.append("")

        # Related Links section - only if provided
        if related_links:
            body_parts.append("## Related Links")
            for link in related_links:
                if isinstance(link, dict):
                    title = link.get("title", "")
                    path = link.get("path", "")
                    connection = link.get("connection", "")
                    body_parts.append(f"- [[{path}|{title}]]" + (f" - {connection}" if connection else ""))
                else:
                    body_parts.append(f"- {link}")
            body_parts.append("")

        body = "\n".join(body_parts)
        return frontmatter, body

    def parse_meeting_content(self, content: str) -> Dict[str, Any]:
        """
        Parse freeform meeting content and extract structured data
        Looks for common patterns like participant lists, action items, etc.

        Returns dict with extracted data that can be passed to build_meeting_note_from_data
        """
        lines = content.split("\n")
        extracted = {
            "attendees": [],
            "discussion": "",
            "action_items": [],
            "decisions": [],
        }

        current_section = None
        discussion_lines = []

        for line in lines:
            line_stripped = line.strip()

            # Detect participant/attendee section
            if re.match(r"^(participants?|attendees?):", line_stripped, re.IGNORECASE):
                current_section = "attendees"
                continue

            # Detect action items section
            if re.match(r"^action items?:", line_stripped, re.IGNORECASE):
                current_section = "action_items"
                continue

            # Detect decisions section
            if re.match(r"^decisions?:", line_stripped, re.IGNORECASE):
                current_section = "decisions"
                continue

            # Extract attendees (look for lines with names, possibly with roles in parentheses)
            if current_section == "attendees":
                # Match patterns like "Alex (Scrum Master)" or "- Alex (SM)" or just "Alex"
                attendee_match = re.match(r"^[-*]?\s*([A-Za-z\s]+?)(?:\s*\(([^)]+)\))?\s*$", line_stripped)
                if attendee_match and len(line_stripped) > 2:
                    name = attendee_match.group(1).strip()
                    role = attendee_match.group(2).strip() if attendee_match.group(2) else None
                    if name and len(name.split()) <= 4:  # Reasonable name length
                        if role:
                            extracted["attendees"].append({"name": name, "role": role})
                        else:
                            extracted["attendees"].append(name)
                elif not line_stripped:
                    current_section = None

            # Collect discussion content
            elif current_section == "action_items":
                # Parse action items
                if line_stripped and line_stripped.startswith("-"):
                    extracted["action_items"].append(line_stripped[1:].strip())
                elif not line_stripped:
                    current_section = None

            elif current_section == "decisions":
                # Parse decisions
                if line_stripped and line_stripped.startswith("-"):
                    extracted["decisions"].append(line_stripped[1:].strip())
                elif not line_stripped:
                    current_section = None

            else:
                # Everything else goes to discussion
                discussion_lines.append(line)

        # Clean up discussion
        extracted["discussion"] = "\n".join(discussion_lines).strip()

        return extracted


# Global instance
template_detector = TemplateDetector()

