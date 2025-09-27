"""
Obsidian MCP Tools Implementation
All 9 tools from the PRD specification using the enhanced ObsidianClient
"""
import os
from typing import Dict, Any, List, Optional
from datetime import datetime
from src.clients.obsidian_client import ObsidianClient, ObsidianAPIError
from ..types import MCPTool


class ObsidianTools:
    """
    Implementation of all 9 MCP tools for Obsidian vault operations
    """

    def __init__(self):
        self.client = None
        self._initialize_client()

    def _initialize_client(self):
        """Initialize ObsidianClient with error handling"""
        try:
            self.client = ObsidianClient()
        except ValueError as e:
            # Client will be None if API key is not set
            print(f"Warning: ObsidianClient not initialized: {e}")
            self.client = None

    def get_tools(self) -> List[MCPTool]:
        """Get all available MCP tools"""
        return [
            # Tool 1: obs_search_notes
            MCPTool(
                name="obs_search_notes",
                description="Search notes in the Obsidian vault using full-text search",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query string to find in notes",
                        },
                        "folder": {
                            "type": "string",
                            "description": "Optional folder to limit search scope (e.g., 'Projects')",
                            "default": "",
                        },
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            ),
            # Tool 2: obs_read_note
            MCPTool(
                name="obs_read_note",
                description="Read the complete content of a specific note",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to the note relative to vault root (e.g., 'Daily Notes/2024-01-15.md')",
                        }
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
            ),
            # Tool 3: obs_create_note
            MCPTool(
                name="obs_create_note",
                description="Create a new note in the Obsidian vault. Automatically applies templates based on folder location.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path where the note should be created (e.g., 'Ideas/New Idea.md')",
                        },
                        "content": {
                            "type": "string",
                            "description": "Content of the new note in Markdown format. If minimal, appropriate template will be applied.",
                        },
                        "create_folders": {
                            "type": "boolean",
                            "description": "Whether to create parent folders if they don't exist",
                            "default": True,
                        },
                        "use_template": {
                            "type": "boolean",
                            "description": "Whether to apply appropriate template based on folder location (daily-notes, projects, areas, etc.)",
                            "default": True,
                        },
                    },
                    "required": ["path", "content"],
                    "additionalProperties": False,
                },
            ),
            # Tool 4: obs_update_note
            MCPTool(
                name="obs_update_note",
                description="Update the complete content of an existing note with format preservation",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to the note to update",
                        },
                        "content": {
                            "type": "string",
                            "description": "New content that will replace the entire note",
                        },
                        "preserve_format": {
                            "type": "boolean",
                            "description": "Whether to preserve existing YAML frontmatter and note structure",
                            "default": True,
                        },
                    },
                    "required": ["path", "content"],
                    "additionalProperties": False,
                },
            ),
            # Tool 5: obs_append_note
            MCPTool(
                name="obs_append_note",
                description="Append content to an existing note",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to the note to append to",
                        },
                        "content": {
                            "type": "string",
                            "description": "Content to append to the note",
                        },
                        "separator": {
                            "type": "string",
                            "description": "Separator between existing and new content",
                            "default": "\n\n",
                        },
                    },
                    "required": ["path", "content"],
                    "additionalProperties": False,
                },
            ),
            # Tool 6: obs_delete_note
            MCPTool(
                name="obs_delete_note",
                description="Delete a note from the Obsidian vault",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to the note to delete",
                        }
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
            ),
            # Tool 7: obs_list_notes
            MCPTool(
                name="obs_list_notes",
                description="List notes in the vault or a specific folder with metadata",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "folder": {
                            "type": "string",
                            "description": "Optional folder to list notes from (e.g., 'Projects'). Leave empty for all notes.",
                            "default": "",
                        }
                    },
                    "additionalProperties": False,
                },
            ),
            # Tool 8: obs_get_vault_structure
            MCPTool(
                name="obs_get_vault_structure",
                description="Get the complete folder and note structure of the vault",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "use_cache": {
                            "type": "boolean",
                            "description": "Whether to use cached structure data if available",
                            "default": True,
                        }
                    },
                    "additionalProperties": False,
                },
            ),
            # Tool 9: obs_execute_command
            MCPTool(
                name="obs_execute_command",
                description="Execute an Obsidian command via the REST API",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "Name of the Obsidian command to execute (e.g., 'app:reload')",
                        },
                        "parameters": {
                            "type": "object",
                            "description": "Optional parameters for the command",
                            "default": {},
                        },
                    },
                    "required": ["command"],
                    "additionalProperties": False,
                },
            ),
            # Tool 10: obs_keyword_search - Simple keyword search
            MCPTool(
                name="obs_keyword_search",
                description="Simple keyword search to find notes containing a specific word or phrase. More flexible than advanced search.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "keyword": {
                            "type": "string",
                            "description": "Keyword or phrase to search for in note content",
                        },
                        "folder": {
                            "type": "string",
                            "description": "Optional folder to limit search scope (e.g., '03_areas', 'Projects'). Leave empty to search all notes.",
                            "default": "",
                        },
                        "case_sensitive": {
                            "type": "boolean",
                            "description": "Whether to perform case-sensitive search",
                            "default": False,
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of notes to return (default: 20)",
                            "default": 20,
                            "minimum": 1,
                            "maximum": 50,
                        },
                    },
                    "required": ["keyword"],
                    "additionalProperties": False,
                },
            ),
        ]

    # =================== Tool Implementations ===================

    async def search_notes(self, query: str, folder: str = "") -> Dict[str, Any]:
        """
        Tool 1: Search notes in the vault
        """
        if not self.client:
            raise ValueError("Obsidian client not initialized. Check OBSIDIAN_API_KEY.")

        try:
            folder_param = folder.strip() if folder else None
            results = await self.client.search_notes(query, folder_param)

            # Format results for MCP response
            formatted_results = []
            for result in results:
                formatted_result = {
                    "path": result.get("path", ""),
                    "snippet": result.get("snippet", ""),
                    "matches": result.get("matches", 0),
                }

                # Add metadata if available
                if "metadata" in result:
                    formatted_result["metadata"] = result["metadata"]

                formatted_results.append(formatted_result)

            response_text = f"Found {len(formatted_results)} results for '{query}'"
            if folder:
                response_text += f" in folder '{folder}'"
            response_text += ":\n\n"

            for i, result in enumerate(
                formatted_results[:10], 1
            ):  # Limit to first 10 for readability
                response_text += f"{i}. **{result['path']}**\n"
                if result.get("snippet"):
                    response_text += f"   {result['snippet']}\n"
                if result.get("matches"):
                    response_text += f"   Matches: {result['matches']}\n"
                response_text += "\n"

            if len(formatted_results) > 10:
                response_text += f"... and {len(formatted_results) - 10} more results"

            return {
                "content": [{"type": "text", "text": response_text}],
                "metadata": {
                    "total_results": len(formatted_results),
                    "query": query,
                    "folder": folder,
                    "results": formatted_results,
                },
            }

        except ObsidianAPIError as e:
            raise ValueError(f"Search failed: {e.message}")
        except Exception as e:
            raise ValueError(f"Unexpected error during search: {str(e)}")

    async def read_note(self, path: str) -> Dict[str, Any]:
        """
        Tool 2: Read note content
        """
        if not self.client:
            raise ValueError("Obsidian client not initialized. Check OBSIDIAN_API_KEY.")

        try:
            content = await self.client.read_note(path)

            # Get metadata if possible
            metadata = {}
            try:
                note_metadata = await self.client.get_note_metadata(path)
                metadata = {
                    "size": note_metadata.size,
                    "modified": note_metadata.modified.isoformat(),
                    "created": note_metadata.created.isoformat()
                    if note_metadata.created
                    else None,
                    "tags": note_metadata.tags,
                }
            except Exception:
                # Continue without metadata if it fails
                pass

            return {
                "content": [
                    {"type": "text", "text": f"# Content of {path}\n\n{content}"}
                ],
                "metadata": {"path": path, "content_length": len(content), **metadata},
            }

        except ObsidianAPIError as e:
            if e.status_code == 404:
                raise ValueError(f"Note not found: {path}")
            raise ValueError(f"Failed to read note: {e.message}")
        except Exception as e:
            raise ValueError(f"Unexpected error reading note: {str(e)}")

    async def create_note(
        self,
        path: str,
        content: str,
        create_folders: bool = True,
        use_template: bool = True,
    ) -> Dict[str, Any]:
        """
        Tool 3: Create a new note with template support
        Automatically applies appropriate template based on folder location
        """
        if not self.client:
            raise ValueError("Obsidian client not initialized. Check OBSIDIAN_API_KEY.")

        try:
            from ..utils.template_utils import template_detector

            final_content = content
            template_applied = False
            note_type = None

            # Apply template if requested and appropriate
            if use_template:
                note_type = template_detector.detect_note_type_from_path(path)
                if note_type:
                    # Check if content already has frontmatter
                    existing_frontmatter, body = template_detector.extract_frontmatter(
                        content
                    )

                    if not existing_frontmatter:
                        # Apply default frontmatter for this note type
                        default_frontmatter = template_detector.get_default_frontmatter(
                            note_type, path
                        )

                        # If no body content provided, use template body
                        if not body.strip():
                            note_name = (
                                path.split("/")[-1]
                                .replace(".md", "")
                                .replace("-", " ")
                                .title()
                            )
                            body = template_detector.get_default_body_template(
                                note_type, note_name
                            )

                        final_content = (
                            template_detector.build_content_with_frontmatter(
                                default_frontmatter, body
                            )
                        )
                        template_applied = True

            success = await self.client.create_note(path, final_content, create_folders)

            if success:
                template_info = (
                    f"\n🎯 Applied {note_type} template" if template_applied else ""
                )

                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"✅ Successfully created note: {path}{template_info}\n\nContent length: {len(final_content)} characters",
                        }
                    ],
                    "metadata": {
                        "path": path,
                        "content_length": len(final_content),
                        "created_at": datetime.now().isoformat(),
                        "folders_created": create_folders,
                        "template_applied": template_applied,
                        "note_type": note_type,
                    },
                }
            else:
                raise ValueError("Note creation returned False")

        except ObsidianAPIError as e:
            if e.status_code == 409:
                raise ValueError(f"Note already exists: {path}")
            raise ValueError(f"Failed to create note: {e.message}")
        except Exception as e:
            raise ValueError(f"Unexpected error creating note: {str(e)}")

    async def update_note(
        self, path: str, content: str, preserve_format: bool = True
    ) -> Dict[str, Any]:
        """
        Tool 4: Update existing note with format preservation
        """
        if not self.client:
            raise ValueError("Obsidian client not initialized. Check OBSIDIAN_API_KEY.")

        try:
            from ..utils.template_utils import template_detector

            final_content = content
            format_preserved = False

            # Preserve existing format if requested
            if preserve_format:
                try:
                    # Read existing note to get its structure
                    existing_content = await self.client.read_note(path)
                    note_type = template_detector.detect_note_type_from_path(path)

                    if note_type:
                        final_content = template_detector.preserve_existing_structure(
                            existing_content, content, note_type
                        )
                        format_preserved = True
                except Exception:
                    # If we can't preserve format, use content as-is
                    pass

            success = await self.client.update_note(path, final_content)

            if success:
                format_info = (
                    f"\n🔒 Preserved existing format" if format_preserved else ""
                )

                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"✅ Successfully updated note: {path}{format_info}\n\nNew content length: {len(final_content)} characters",
                        }
                    ],
                    "metadata": {
                        "path": path,
                        "content_length": len(final_content),
                        "updated_at": datetime.now().isoformat(),
                        "format_preserved": format_preserved,
                    },
                }
            else:
                raise ValueError("Note update returned False")

        except ObsidianAPIError as e:
            if e.status_code == 404:
                raise ValueError(f"Note not found: {path}")
            raise ValueError(f"Failed to update note: {e.message}")
        except Exception as e:
            raise ValueError(f"Unexpected error updating note: {str(e)}")

    async def append_note(
        self, path: str, content: str, separator: str = "\n\n"
    ) -> Dict[str, Any]:
        """
        Tool 5: Append content to existing note
        """
        if not self.client:
            raise ValueError("Obsidian client not initialized. Check OBSIDIAN_API_KEY.")

        try:
            success = await self.client.append_note(path, content, separator)

            if success:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"✅ Successfully appended to note: {path}\n\nAppended content length: {len(content)} characters",
                        }
                    ],
                    "metadata": {
                        "path": path,
                        "appended_length": len(content),
                        "separator": separator,
                        "appended_at": datetime.now().isoformat(),
                    },
                }
            else:
                raise ValueError("Note append returned False")

        except ObsidianAPIError as e:
            if e.status_code == 404:
                raise ValueError(f"Note not found: {path}")
            raise ValueError(f"Failed to append to note: {e.message}")
        except Exception as e:
            raise ValueError(f"Unexpected error appending to note: {str(e)}")

    async def delete_note(self, path: str) -> Dict[str, Any]:
        """
        Tool 6: Delete a note
        """
        if not self.client:
            raise ValueError("Obsidian client not initialized. Check OBSIDIAN_API_KEY.")

        try:
            success = await self.client.delete_note(path)

            if success:
                return {
                    "content": [
                        {"type": "text", "text": f"✅ Successfully deleted note: {path}"}
                    ],
                    "metadata": {
                        "path": path,
                        "deleted_at": datetime.now().isoformat(),
                    },
                }
            else:
                raise ValueError("Note deletion returned False")

        except ObsidianAPIError as e:
            if e.status_code == 404:
                raise ValueError(f"Note not found: {path}")
            raise ValueError(f"Failed to delete note: {e.message}")
        except Exception as e:
            raise ValueError(f"Unexpected error deleting note: {str(e)}")

    async def list_notes(self, folder: str = "") -> Dict[str, Any]:
        """
        Tool 7: List notes with metadata
        """
        if not self.client:
            raise ValueError("Obsidian client not initialized. Check OBSIDIAN_API_KEY.")

        try:
            folder_param = folder.strip() if folder else None
            notes = await self.client.list_notes(folder_param)

            # Format notes for response
            response_text = f"Found {len(notes)} notes"
            if folder:
                response_text += f" in folder '{folder}'"
            response_text += ":\n\n"

            notes_data = []
            for note in notes:
                note_info = {
                    "path": note.path,
                    "name": note.name,
                    "size": note.size,
                    "modified": note.modified.isoformat(),
                    "created": note.created.isoformat() if note.created else None,
                    "tags": note.tags or [],
                }
                notes_data.append(note_info)

                # Add to response text
                response_text += f"📝 **{note.name}**\n"
                response_text += f"   Path: {note.path}\n"
                response_text += f"   Size: {note.size:,} bytes\n"
                response_text += (
                    f"   Modified: {note.modified.strftime('%Y-%m-%d %H:%M')}\n"
                )
                if note.tags:
                    response_text += f"   Tags: {', '.join(note.tags)}\n"
                response_text += "\n"

            return {
                "content": [{"type": "text", "text": response_text}],
                "metadata": {
                    "total_notes": len(notes),
                    "folder": folder,
                    "notes": notes_data,
                },
            }

        except ObsidianAPIError as e:
            raise ValueError(f"Failed to list notes: {e.message}")
        except Exception as e:
            raise ValueError(f"Unexpected error listing notes: {str(e)}")

    async def get_vault_structure(self, use_cache: bool = True) -> Dict[str, Any]:
        """
        Tool 8: Get complete vault structure
        """
        if not self.client:
            raise ValueError("Obsidian client not initialized. Check OBSIDIAN_API_KEY.")

        try:
            structure = await self.client.get_vault_structure(use_cache)

            # Build response text
            response_text = f"# Vault Structure\n\n"
            response_text += f"**Root:** {structure.root_path}\n"
            response_text += f"**Total Notes:** {structure.total_notes}\n"
            response_text += f"**Total Folders:** {structure.total_folders}\n\n"

            # Add folder structure
            response_text += "## Folder Structure\n\n"
            for folder in structure.folders:
                indent = "  " * folder.path.count("/")
                response_text += f"{indent}📁 {folder.name}/ ({folder.notes_count} notes, {folder.subfolders_count} subfolders)\n"

            # Add notes overview
            response_text += "\n## Notes Overview\n\n"
            for note in structure.notes[:20]:  # Limit to first 20
                folder_name = (
                    "/".join(note.path.split("/")[:-1]) if "/" in note.path else "Root"
                )
                response_text += (
                    f"📝 {note.name} ({note.size:,} bytes) in {folder_name}\n"
                )

            if len(structure.notes) > 20:
                response_text += f"\n... and {len(structure.notes) - 20} more notes"

            # Prepare metadata
            folders_data = [
                {
                    "path": folder.path,
                    "name": folder.name,
                    "parent": folder.parent,
                    "notes_count": folder.notes_count,
                    "subfolders_count": folder.subfolders_count,
                }
                for folder in structure.folders
            ]

            notes_data = [
                {
                    "path": note.path,
                    "name": note.name,
                    "size": note.size,
                    "modified": note.modified.isoformat(),
                    "created": note.created.isoformat() if note.created else None,
                }
                for note in structure.notes
            ]

            return {
                "content": [{"type": "text", "text": response_text}],
                "metadata": {
                    "root_path": structure.root_path,
                    "total_notes": structure.total_notes,
                    "total_folders": structure.total_folders,
                    "folders": folders_data,
                    "notes": notes_data,
                    "cached": use_cache,
                },
            }

        except ObsidianAPIError as e:
            raise ValueError(f"Failed to get vault structure: {e.message}")
        except Exception as e:
            raise ValueError(f"Unexpected error getting vault structure: {str(e)}")

    async def execute_command(
        self, command: str, parameters: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Tool 9: Execute Obsidian command
        """
        if not self.client:
            raise ValueError("Obsidian client not initialized. Check OBSIDIAN_API_KEY.")

        try:
            if parameters is None:
                parameters = {}

            result = await self.client.execute_command(command, **parameters)

            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"✅ Successfully executed command: {command}\n\nResult: {result}",
                    }
                ],
                "metadata": {
                    "command": command,
                    "parameters": parameters,
                    "executed_at": datetime.now().isoformat(),
                    "result": result,
                },
            }

        except ObsidianAPIError as e:
            raise ValueError(f"Failed to execute command '{command}': {e.message}")
        except Exception as e:
            raise ValueError(f"Unexpected error executing command: {str(e)}")

    async def keyword_search(
        self,
        keyword: str,
        folder: str = "",
        case_sensitive: bool = False,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        Tool 10: Simple keyword search in notes
        """
        if not self.client:
            raise ValueError("Obsidian client not initialized. Check OBSIDIAN_API_KEY.")

        if not keyword.strip():
            raise ValueError("Keyword cannot be empty")

        try:
            # Get all notes (with optional folder filtering)
            all_notes = await self.client.list_notes(folder if folder else None)

            # Search for keyword in note content
            matching_notes = []
            search_keyword = keyword if case_sensitive else keyword.lower()

            for note in all_notes:
                try:
                    # Read note content
                    content = await self.client.read_note(note.path)
                    search_content = content if case_sensitive else content.lower()

                    # Check if keyword is in content
                    if search_keyword in search_content:
                        # Find context around the keyword
                        context = self._extract_context(
                            content, keyword, case_sensitive
                        )

                        matching_notes.append(
                            {
                                "path": note.path,
                                "name": note.name,
                                "size": note.size,
                                "modified": note.modified.isoformat(),
                                "context": context,
                                "folder": os.path.dirname(note.path)
                                if os.path.dirname(note.path)
                                else "root",
                            }
                        )

                        # Stop if we've reached the limit
                        if len(matching_notes) >= limit:
                            break

                except Exception as e:
                    # Skip notes that can't be read
                    continue

            # Sort by relevance (more occurrences first) then by modification date
            matching_notes.sort(key=lambda x: x["modified"], reverse=True)

            # Create response
            total_found = len(matching_notes)
            search_summary = f"Found {total_found} note{'s' if total_found != 1 else ''} containing '{keyword}'"

            if folder:
                search_summary += f" in folder '{folder}'"

            # Format results
            results_text = f"# Keyword Search Results\n\n**Query:** {keyword}\n"
            if folder:
                results_text += f"**Folder:** {folder}\n"
            results_text += f"**Total Found:** {total_found}\n"
            results_text += (
                f"**Case Sensitive:** {'Yes' if case_sensitive else 'No'}\n\n"
            )

            if total_found == 0:
                results_text += "No notes found containing the specified keyword.\n"
            else:
                results_text += "## Matching Notes\n\n"
                for i, note in enumerate(matching_notes, 1):
                    results_text += f"### {i}. {note['name']}\n"
                    results_text += f"**Path:** {note['path']}\n"
                    results_text += f"**Folder:** {note['folder']}\n"
                    results_text += f"**Size:** {note['size']} bytes\n"
                    results_text += f"**Modified:** {note['modified']}\n"
                    results_text += f"**Context:** {note['context']}\n\n"

            return {
                "content": [
                    {
                        "type": "text",
                        "text": results_text,
                    }
                ],
                "metadata": {
                    "keyword": keyword,
                    "folder": folder,
                    "case_sensitive": case_sensitive,
                    "total_found": total_found,
                    "limit": limit,
                    "matching_notes": matching_notes,
                },
            }

        except Exception as e:
            raise ValueError(f"Keyword search failed: {str(e)}")

    def _extract_context(
        self, content: str, keyword: str, case_sensitive: bool = False
    ) -> str:
        """Extract context around the keyword in the content"""
        search_content = content if case_sensitive else content.lower()
        search_keyword = keyword if case_sensitive else keyword.lower()

        # Find the first occurrence of the keyword
        index = search_content.find(search_keyword)
        if index == -1:
            return "Keyword not found"

        # Extract context (50 characters before and after)
        start = max(0, index - 50)
        end = min(len(content), index + len(keyword) + 50)

        context = content[start:end].strip()

        # Add ellipsis if we truncated
        if start > 0:
            context = "..." + context
        if end < len(content):
            context = context + "..."

        return context

    # =================== Tool Dispatcher ===================

    async def execute_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a tool by name with given arguments
        """
        tool_methods = {
            "obs_search_notes": self.search_notes,
            "obs_read_note": self.read_note,
            "obs_create_note": self.create_note,
            "obs_update_note": self.update_note,
            "obs_append_note": self.append_note,
            "obs_delete_note": self.delete_note,
            "obs_list_notes": self.list_notes,
            "obs_get_vault_structure": self.get_vault_structure,
            "obs_execute_command": self.execute_command,
            "obs_keyword_search": self.keyword_search,
        }

        if tool_name not in tool_methods:
            raise ValueError(f"Unknown tool: {tool_name}")

        method = tool_methods[tool_name]

        try:
            return await method(**arguments)
        except TypeError as e:
            raise ValueError(f"Invalid arguments for tool '{tool_name}': {str(e)}")
        except Exception as e:
            # Re-raise with tool context
            raise ValueError(f"Tool '{tool_name}' failed: {str(e)}")


# Global instance
obsidian_tools = ObsidianTools()
