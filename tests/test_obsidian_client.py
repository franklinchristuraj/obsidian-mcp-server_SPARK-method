#!/usr/bin/env python3
"""
Test script for the filesystem-native ObsidianClient
Tests all CRUD operations and vault management features against a
disposable tmp-filesystem vault (not the real vault - this used to hit a
live Obsidian REST API, which no longer exists).
"""
import asyncio
import os
import tempfile
from datetime import datetime
from pathlib import Path

from src.clients.obsidian_client import ObsidianClient, ObsidianAPIError


def _make_tmp_vault() -> str:
    root = Path(tempfile.mkdtemp(prefix="obsidian-client-test-"))
    for scope in ("personal", "passion", "work"):
        (root / scope).mkdir()
    return str(root)


async def test_obsidian_client():
    """Test all ObsidianClient functionality"""

    print("🧪 Testing Filesystem-Native ObsidianClient")
    print("=" * 60)

    vault_path = _make_tmp_vault()
    print(f"📁 Tmp vault: {vault_path}")

    try:
        os.environ["OBSIDIAN_VAULT_PATH"] = vault_path
        client = ObsidianClient()

        # Test 1: Health Check
        print("\n1️⃣ Testing health check...")
        is_healthy = await client.health_check()
        print(f"   {'✅' if is_healthy else '❌'} Vault path readable: {is_healthy}")

        # Test 2: Get Vault Info
        print("\n2️⃣ Testing vault info...")
        vault_info = await client.get_vault_info()
        print(f"   ✅ Vault: {vault_info.get('name', 'Unknown')}")
        print(f"   📁 Path: {vault_info.get('path', 'Unknown')}")

        # Test 3: Get Vault Structure (empty vault)
        print("\n3️⃣ Testing vault structure...")
        structure = await client.get_vault_structure()
        print(
            f"   ✅ Found {structure.total_notes} notes in {structure.total_folders} folders"
        )

        # Test 4: Create Test Note
        test_note_path = f"work/Test/MCP-Test-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
        test_content = f"""# MCP Test Note

Created at: {datetime.now().isoformat()}

This is a test note created by the Obsidian MCP Server.

#mcp #test #automation
"""

        print("\n4️⃣ Testing note creation...")
        success = await client.create_note(test_note_path, test_content)
        print(f"   {'✅' if success else '❌'} Created test note: {test_note_path}")

        # Test 5: Read the created note
        print("\n5️⃣ Testing note reading...")
        content = await client.read_note(test_note_path)
        print(f"   ✅ Read note content: {len(content)} characters")
        print(f"   {'✅' if 'MCP Test Note' in content else '❌'} Content verification")

        # Test 6: Update the note
        print("\n6️⃣ Testing note update...")
        updated_content = test_content + f"\n\n## Updated\nModified at: {datetime.now().isoformat()}"
        success = await client.update_note(test_note_path, updated_content)
        new_content = await client.read_note(test_note_path)
        print(f"   {'✅' if success and 'Modified at:' in new_content else '❌'} Updated note")

        # Test 7: Append to note
        print("\n7️⃣ Testing note append...")
        append_content = f"\n## Appended Section\nAppended at: {datetime.now().isoformat()}"
        success = await client.append_note(test_note_path, append_content)
        final_content = await client.read_note(test_note_path)
        print(f"   {'✅' if success and 'Appended Section' in final_content else '❌'} Appended to note")

        # Test 8: Get note metadata
        print("\n8️⃣ Testing note metadata...")
        metadata = await client.get_note_metadata(test_note_path)
        print(f"   ✅ Got metadata for: {metadata.path}")
        print(f"   📏 Size: {metadata.size} bytes")

        # Test 9: Get vault statistics
        print("\n9️⃣ Testing vault statistics...")
        stats = await client.get_stats()
        print(f"   ✅ Vault Statistics: {stats['total_notes']} notes, {stats['total_size_mb']} MB")

        # Test 10: Folder operations
        print("\n🔟 Testing folder operations...")
        root_contents = await client.get_folder_contents("")
        print(
            f"   ✅ Root folder: {root_contents['total_notes']} notes, {root_contents['total_subfolders']} subfolders"
        )

        # Test 11: Cleanup - Delete test note (moves to .trash/)
        print("\n1️⃣1️⃣ Testing note deletion...")
        success = await client.delete_note(test_note_path)
        exists = await client.note_exists(test_note_path)
        trash_hit = list(Path(vault_path).glob(".trash/**/*.md"))
        print(f"   {'✅' if success and not exists else '❌'} Deleted test note")
        print(f"   {'✅' if trash_hit else '❌'} Landed in .trash/: {[str(p) for p in trash_hit]}")

        print("\n" + "=" * 60)
        print("🎉 ObsidianClient testing completed!")

    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        print(f"Error type: {type(e).__name__}")
        raise
    finally:
        import shutil

        shutil.rmtree(vault_path, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(test_obsidian_client())
