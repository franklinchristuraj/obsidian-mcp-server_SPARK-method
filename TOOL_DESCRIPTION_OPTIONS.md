# Obsidian MCP Server - Tool Name & Description Options

## Option 1: Concise & Action-Oriented (Recommended)

**Tool Name:** `obsidian_vault_manager`

**Description:**
```
MCP server providing comprehensive Obsidian vault operations for AI assistants. 
Use this server when you need to read, create, update, delete, or search notes in an Obsidian vault. 
Includes 12 specialized tools for note management, search, vault exploration, and daily note operations. 
Automatically applies templates based on folder location (daily notes, projects, areas) and preserves 
note formatting during edits. Supports full-text search, keyword search, note existence checks, 
and date-range filtering for daily notes.
```

**When to use:**
- Reading or writing Obsidian notes
- Searching vault content
- Creating notes with proper templates
- Managing daily notes
- Exploring vault structure
- Checking if notes exist before operations

---

## Option 2: Feature-Focused

**Tool Name:** `obsidian_mcp_server`

**Description:**
```
Model Context Protocol server for Obsidian vault integration. Provides 12 tools for complete note 
lifecycle management: search (full-text and keyword), CRUD operations, vault structure browsing, 
daily note filtering, and note existence checks. Features automatic template application for 
different note types (daily notes, projects, areas) and format-preserving updates. Ideal for 
AI assistants that need to interact with Obsidian knowledge bases, create structured notes, 
or search existing content.
```

**When to use:**
- Any Obsidian vault operation
- Creating structured notes with templates
- Searching existing notes
- Managing daily notes by date range
- Verifying note existence before operations

---

## Option 3: Detailed & Comprehensive

**Tool Name:** `obsidian_vault_operations`

**Description:**
```
Complete MCP server for Obsidian vault management with 12 specialized tools. Capabilities include:
- Note operations: read, create, update, append, delete with format preservation
- Search: full-text search with folder filtering, keyword search with case sensitivity options
- Vault exploration: list notes with metadata, get complete vault structure, browse folders
- Daily notes: list daily notes by date range, check note existence with last modified dates
- Template system: automatic template application based on folder location (PARA method support)
- Command execution: run Obsidian commands via REST API

Use this server for any task involving Obsidian notes, vault organization, or knowledge base 
interactions. Templates are automatically applied for daily notes, projects, areas, seeds, 
resources, and knowledge notes. All operations preserve existing note formatting and YAML frontmatter.
```

**When to use:**
- Reading or writing any Obsidian note
- Searching vault content (full-text or keyword)
- Creating notes with automatic template application
- Managing daily notes within date ranges
- Exploring vault structure and organization
- Checking note existence before operations
- Executing Obsidian commands

---

## Option 4: Simple & Direct

**Tool Name:** `obsidian_notes`

**Description:**
```
MCP server for Obsidian vault access. Provides tools to read, write, search, and manage notes 
in an Obsidian vault. Includes automatic template support and format preservation. Use when 
working with Obsidian notes or knowledge bases.
```

**When to use:**
- Any Obsidian note operation
- Searching vault content
- Creating or updating notes

---

## Recommendation

**I recommend Option 1** (`obsidian_vault_manager`) because it:
- ✅ Clearly indicates the purpose (vault management)
- ✅ Mentions key capabilities without being overwhelming
- ✅ Highlights the template system (important differentiator)
- ✅ Includes specific use cases
- ✅ Balanced length (informative but concise)

---

## Quick Reference: Available Tools

The server provides these 12 Obsidian tools (all prefixed with `obs_`):

1. **obs_search_notes** - Full-text search with folder filtering
2. **obs_read_note** - Read note content and metadata
3. **obs_create_note** - Create notes with automatic templates
4. **obs_update_note** - Update notes with format preservation
5. **obs_append_note** - Append content to existing notes
6. **obs_delete_note** - Delete notes from vault
7. **obs_list_notes** - List notes with metadata
8. **obs_get_vault_structure** - Get complete vault organization
9. **obs_execute_command** - Execute Obsidian commands
10. **obs_keyword_search** - Simple keyword search
11. **obs_check_note_exists** - Check note existence and last modified date
12. **obs_list_daily_notes** - List daily notes by date range

Plus 1 system tool:
- **ping** - Connectivity testing


