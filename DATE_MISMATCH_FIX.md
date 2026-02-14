# Date Mismatch Detection Fix

## Issue Identified

**User Request:** Update note from 2025-02-04 to 2026-02-04

**What Happened:**
- Claude sent content with `creation-date: 2026-02-04` and heading "2026"
- But used path `06_daily-notes/2025-02-04.md` (wrong year)
- Server correctly updated the note at the path Claude specified
- Result: Note at `2025-02-04.md` now has 2026 dates in content

**Root Cause:** Claude-side error - Claude should have updated the path to match the content date.

## Server-Side Enhancement

Added date mismatch detection to help catch this issue:

### What It Does

1. **Detects Date Mismatches** for daily notes:
   - Extracts date from file path (e.g., `2025-02-04` from `2025-02-04.md`)
   - Extracts date from content frontmatter (`creation-date` field)
   - Compares dates and warns if they don't match

2. **Provides Warning Message:**
   ```
   ⚠️  Date mismatch detected: Path has 2025-02-04 but content has 2026-02-04. 
   Consider updating the path to match the content date.
   ```

3. **Also Checks Year in Heading:**
   - Extracts year from content heading
   - Warns if year doesn't match path year

### Implementation

Added to `update_note` function in `obsidian_tools.py`:
- Checks if path contains "daily-notes" or "06_daily-notes"
- Extracts dates using regex patterns
- Compares dates and generates warning if mismatch detected
- Warning is included in response message and metadata

## Testing

To test the date mismatch detection:

```bash
# Update note with mismatched date
curl -H "Authorization: Bearer API_KEY" \
     -H "Content-Type: application/json" \
     -X POST https://mcp.ziksaka.com/mcp \
     -d '{
       "jsonrpc":"2.0",
       "method":"tools/call",
       "params":{
         "name":"obs_update_note",
         "arguments":{
           "path":"06_daily-notes/2025-02-04.md",
           "content":"---\ncreation-date: 2026-02-04\n---\n# Daily Note for 2026"
         }
       },
       "id":1
     }'
```

Expected response should include:
```
⚠️  Date mismatch detected: Path has 2025-02-04 but content has 2026-02-04...
```

## Recommendations for Claude

When updating daily notes with date changes:

1. **Detect Date Changes:** If content date differs from path date, update the path
2. **Use Correct Tool:** Consider using `obs_create_note` with new path, then `obs_delete_note` for old path
3. **Or Rename:** Use a rename/move operation if available

## Current Status

- ✅ Server-side validation added
- ✅ Warning messages implemented
- ✅ Service restarted with fix
- ⚠️  Note at `2025-02-04.md` still has 2026 dates (needs manual fix)

## Manual Fix Required

The note `06_daily-notes/2025-02-04.md` currently has:
- Path: `2025-02-04.md` (wrong)
- Content: `creation-date: 2026-02-04` (correct)

**Options:**
1. Move/rename the file to `2026-02-04.md`
2. Or update the content back to 2025 dates
3. Or delete `2025-02-04.md` and create new `2026-02-04.md` with correct content
