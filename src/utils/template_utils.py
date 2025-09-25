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
        self.folder_templates = {
            "06_daily-notes": "daily-note",
            "02_projects": "project",
            "03_areas": "area",
            "01_seeds": "seed",
            "04_resources": "resource",
            "05_knowledge": "knowledge",
        }

    def detect_note_type_from_path(self, path: str) -> Optional[str]:
        """Detect note type from file path"""
        for folder, note_type in self.folder_templates.items():
            if path.startswith(folder + "/") or path.startswith(folder):
                return note_type
        return None

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


# Global instance
template_detector = TemplateDetector()

