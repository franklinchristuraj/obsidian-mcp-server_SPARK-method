# Frontmatter Template Variable Fix

## Issue Identified

The note `06_daily-notes/2025-02-04.md` was created successfully, but had broken frontmatter:

**Before:**
```yaml
---
creation-date:
  '{ date:YYYY-MM-DD }': null
type: daily-note
---
```

**After Fix:**
```yaml
---
creation-date: 2025-02-04
type: daily-note
---
```

## Root Cause

1. **Template Variable Syntax Mismatch**: The template file uses Obsidian template syntax `{ date:YYYY-MM-DD }` which is not automatically processed by Python's template system
2. **Preserve Format Logic**: When updating notes with `preserve_format: true`, the broken template variable was preserved from the existing note
3. **No Template Variable Substitution**: The `apply_template` function only handled Python-style `{{variable}}` syntax, not Obsidian's `{ date:... }` syntax

## Fixes Applied

### 1. Fixed `preserve_existing_structure` function
- Now skips broken template variables when preserving format
- Removes null values that are template placeholders
- Cleans up frontmatter before merging

### 2. Enhanced `apply_template` function
- Now handles Obsidian template variables like `{ date:YYYY-MM-DD }`
- Replaces common Obsidian date formats with actual dates
- Handles both single and double-quoted template variables

### 3. Fixed Existing Note
- Manually fixed the broken frontmatter in `2025-02-04.md`
- Replaced broken template variable with actual date

## Testing

To verify the fix works:

1. **Test note creation:**
   ```bash
   curl -H "Authorization: Bearer API_KEY" \
        -H "Content-Type: application/json" \
        -X POST https://mcp.ziksaka.com/mcp \
        -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"obs_create_note","arguments":{"path":"06_daily-notes/test-date.md","content":"# Test"}},"id":1}'
   ```

2. **Check frontmatter:**
   ```bash
   cat /home/franklinchris/obsidian/config/franklin-vault/06_daily-notes/test-date.md | head -10
   ```

3. **Verify no broken template variables:**
   - Frontmatter should have `creation-date: YYYY-MM-DD` format
   - No `{ date:... }` template variables should remain

## Prevention

The fixes ensure that:
- New notes created from templates will have proper date substitution
- Updates with `preserve_format: true` won't preserve broken template variables
- Obsidian template syntax is properly converted to actual values

## Next Steps

1. ✅ Fix applied to code
2. ✅ Existing note fixed
3. ✅ Service restarted
4. ⏳ Test with Claude connector to verify end-to-end
