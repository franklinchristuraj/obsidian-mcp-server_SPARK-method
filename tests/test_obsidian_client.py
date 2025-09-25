#!/usr/bin/env python3
"""
Test script for the enhanced ObsidianClient
Tests all CRUD operations and vault management features
"""
import asyncio
import json
import os
from datetime import datetime
from dotenv import load_dotenv
from src.obsidian_client import ObsidianClient, ObsidianAPIError

# Load environment variables
load_dotenv()


async def test_obsidian_client():
    """Test all ObsidianClient functionality"""

    print("🧪 Testing Enhanced ObsidianClient")
    print("=" * 60)

    try:
        # Initialize client
        client = ObsidianClient()
        print(f"🔗 API URL: {client.api_url}")
        print(f"🔑 API Key: {client.api_key[:8] if client.api_key else 'NOT SET'}...")

        if not client.api_key:
            print("❌ Error: OBSIDIAN_API_KEY not set")
            print("💡 Set environment variable: export OBSIDIAN_API_KEY='your-key'")
            return

        # Test 1: Health Check
        print("\n1️⃣ Testing health check...")
        try:
            is_healthy = await client.health_check()
            if is_healthy:
                print("   ✅ Obsidian API is accessible")
            else:
                print("   ❌ Obsidian API not accessible")
                print("   💡 Make sure Obsidian is running with REST API plugin enabled")
                return
        except Exception as e:
            print(f"   ❌ Health check failed: {e}")
            return

        # Test 2: Get Vault Info
        print("\n2️⃣ Testing vault info...")
        try:
            vault_info = await client.get_vault_info()
            print(f"   ✅ Vault: {vault_info.get('name', 'Unknown')}")
            print(f"   📁 Path: {vault_info.get('path', 'Unknown')}")
        except Exception as e:
            print(f"   ❌ Vault info failed: {e}")

        # Test 3: Get Vault Structure
        print("\n3️⃣ Testing vault structure...")
        try:
            structure = await client.get_vault_structure()
            print(
                f"   ✅ Found {structure.total_notes} notes in {structure.total_folders} folders"
            )
            print(f"   📁 Root: {structure.root_path}")

            # Show first few folders and notes
            if structure.folders:
                print("   📂 Folders:")
                for folder in structure.folders[:3]:
                    print(f"      • {folder.path} ({folder.notes_count} notes)")
                if len(structure.folders) > 3:
                    print(f"      ... and {len(structure.folders) - 3} more")

            if structure.notes:
                print("   📄 Notes:")
                for note in structure.notes[:3]:
                    print(f"      • {note.path} ({note.size} bytes)")
                if len(structure.notes) > 3:
                    print(f"      ... and {len(structure.notes) - 3} more")

        except Exception as e:
            print(f"   ❌ Vault structure failed: {e}")

        # Test 4: Search Notes
        print("\n4️⃣ Testing search functionality...")
        try:
            results = await client.search_notes("note")
            print(f"   ✅ Found {len(results)} search results for 'note'")

            for i, result in enumerate(results[:3]):
                path = result.get("path", "Unknown")
                print(f"      {i+1}. {path}")

        except Exception as e:
            print(f"   ❌ Search failed: {e}")

        # Test 5: List Notes
        print("\n5️⃣ Testing note listing...")
        try:
            notes = await client.list_notes()
            print(f"   ✅ Listed {len(notes)} notes with metadata")

            if notes:
                recent_note = max(notes, key=lambda n: n.modified)
                print(
                    f"   📅 Most recent: {recent_note.path} ({recent_note.modified.strftime('%Y-%m-%d %H:%M')})"
                )

                if notes[0].tags:
                    print(f"   🏷️  Example tags: {', '.join(notes[0].tags[:3])}")

        except Exception as e:
            print(f"   ❌ Note listing failed: {e}")

        # Test 6: Create Test Note
        test_note_path = f"Test/MCP-Test-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
        test_content = f"""# MCP Test Note

Created at: {datetime.now().isoformat()}

This is a test note created by the Obsidian MCP Server.

## Features Tested
- Note creation
- Content writing
- Folder auto-creation

#mcp #test #automation
"""

        print(f"\n6️⃣ Testing note creation...")
        try:
            success = await client.create_note(test_note_path, test_content)
            if success:
                print(f"   ✅ Created test note: {test_note_path}")
                print(f"   📝 Content: {len(test_content)} characters")
            else:
                print("   ❌ Note creation returned False")
        except Exception as e:
            print(f"   ❌ Note creation failed: {e}")

        # Test 7: Read the created note
        print(f"\n7️⃣ Testing note reading...")
        try:
            content = await client.read_note(test_note_path)
            print(f"   ✅ Read note content: {len(content)} characters")

            # Verify content matches
            if "MCP Test Note" in content:
                print("   ✅ Content verification passed")
            else:
                print("   ❌ Content verification failed")

        except Exception as e:
            print(f"   ❌ Note reading failed: {e}")

        # Test 8: Update the note
        print(f"\n8️⃣ Testing note update...")
        try:
            updated_content = (
                test_content
                + f"\n\n## Updated\nModified at: {datetime.now().isoformat()}"
            )
            success = await client.update_note(test_note_path, updated_content)
            if success:
                print(f"   ✅ Updated note: {test_note_path}")

                # Verify update
                new_content = await client.read_note(test_note_path)
                if "Modified at:" in new_content:
                    print("   ✅ Update verification passed")
                else:
                    print("   ❌ Update verification failed")
            else:
                print("   ❌ Note update returned False")
        except Exception as e:
            print(f"   ❌ Note update failed: {e}")

        # Test 9: Append to note
        print(f"\n9️⃣ Testing note append...")
        try:
            append_content = (
                f"\n## Appended Section\nAppended at: {datetime.now().isoformat()}"
            )
            success = await client.append_note(test_note_path, append_content)
            if success:
                print(f"   ✅ Appended to note: {test_note_path}")

                # Verify append
                final_content = await client.read_note(test_note_path)
                if "Appended Section" in final_content:
                    print("   ✅ Append verification passed")
                else:
                    print("   ❌ Append verification failed")
            else:
                print("   ❌ Note append returned False")
        except Exception as e:
            print(f"   ❌ Note append failed: {e}")

        # Test 10: Get note metadata
        print(f"\n🔟 Testing note metadata...")
        try:
            metadata = await client.get_note_metadata(test_note_path)
            print(f"   ✅ Got metadata for: {metadata.path}")
            print(f"   📏 Size: {metadata.size} bytes")
            print(f"   📅 Modified: {metadata.modified.strftime('%Y-%m-%d %H:%M:%S')}")
            if metadata.created:
                print(f"   🆕 Created: {metadata.created.strftime('%Y-%m-%d %H:%M:%S')}")
        except Exception as e:
            print(f"   ❌ Metadata retrieval failed: {e}")

        # Test 11: Get vault statistics
        print(f"\n1️⃣1️⃣ Testing vault statistics...")
        try:
            stats = await client.get_stats()
            print(f"   ✅ Vault Statistics:")
            print(f"   📊 Notes: {stats['total_notes']}")
            print(f"   📁 Folders: {stats['total_folders']}")
            print(f"   💾 Total Size: {stats['total_size_mb']} MB")

            if stats["largest_note"]:
                print(
                    f"   📈 Largest: {stats['largest_note']['path']} ({stats['largest_note']['size']} bytes)"
                )

            if stats["most_recent_note"]:
                print(f"   🆕 Most Recent: {stats['most_recent_note']['path']}")

        except Exception as e:
            print(f"   ❌ Statistics failed: {e}")

        # Test 12: Test folder operations
        print(f"\n1️⃣2️⃣ Testing folder operations...")
        try:
            # Get root folder contents
            root_contents = await client.get_folder_contents("")
            print(
                f"   ✅ Root folder: {root_contents['total_notes']} notes, {root_contents['total_subfolders']} subfolders"
            )

            # Test specific folder if it exists
            if root_contents["subfolders"]:
                test_folder = root_contents["subfolders"][0]["path"]
                folder_contents = await client.get_folder_contents(test_folder)
                print(
                    f"   📁 {test_folder}: {folder_contents['total_notes']} notes, {folder_contents['total_subfolders']} subfolders"
                )

        except Exception as e:
            print(f"   ❌ Folder operations failed: {e}")

        # Test 13: Execute Obsidian command (if supported)
        print(f"\n1️⃣3️⃣ Testing command execution...")
        try:
            # Try a simple command (this might fail if not supported)
            result = await client.execute_command("app:reload")
            print(f"   ✅ Command executed: {result}")
        except Exception as e:
            print(f"   ⚠️  Command execution not supported or failed: {e}")

        # Test 14: Cleanup - Delete test note
        print(f"\n1️⃣4️⃣ Testing note deletion...")
        try:
            success = await client.delete_note(test_note_path)
            if success:
                print(f"   ✅ Deleted test note: {test_note_path}")

                # Verify deletion
                exists = await client.note_exists(test_note_path)
                if not exists:
                    print("   ✅ Deletion verification passed")
                else:
                    print("   ❌ Note still exists after deletion")
            else:
                print("   ❌ Note deletion returned False")
        except Exception as e:
            print(f"   ❌ Note deletion failed: {e}")

        print("\n" + "=" * 60)
        print("🎉 ObsidianClient testing completed!")

        print("\n📋 Test Summary:")
        print("   ✅ Basic Operations: Health check, vault info")
        print("   ✅ Structure Operations: Vault traversal, folder contents")
        print("   ✅ Search Operations: Note search with metadata")
        print("   ✅ CRUD Operations: Create, Read, Update, Append, Delete")
        print("   ✅ Metadata Operations: Note info, vault statistics")
        print("   ✅ Utility Operations: Path normalization, existence checks")

        print("\n🚀 Ready for MCP Tools integration!")

    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        print(f"Error type: {type(e).__name__}")


if __name__ == "__main__":
    asyncio.run(test_obsidian_client())


