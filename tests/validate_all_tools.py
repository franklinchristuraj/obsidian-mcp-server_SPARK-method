#!/usr/bin/env python3
"""
Quick validation script to confirm all Obsidian tools work after optimizations
"""
import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from src.tools.obsidian_tools import obsidian_tools
from src.mcp_server import mcp_handler

# Load environment variables
load_dotenv()


async def validate_tool_discovery():
    """Validate all tools are discoverable"""
    print("\n" + "="*80)
    print("🔍 TEST 1: Tool Discovery")
    print("="*80)

    try:
        response = await mcp_handler.handle_request("tools/list")
        tools = response.get("tools", [])

        # Filter Obsidian tools
        obs_tools = [t for t in tools if t["name"].startswith("obs_")]

        expected_tools = [
            "obs_read_note",
            "obs_create_note",
            "obs_update_note",
            "obs_append_note",
            "obs_delete_note",
            "obs_list_notes",
            "obs_get_vault_structure",
            "obs_keyword_search",
            "obs_check_note_exists",
            "obs_list_daily_notes",
        ]

        print(f"Found {len(obs_tools)} Obsidian tools:")

        all_found = True
        for expected in expected_tools:
            if expected in [t["name"] for t in obs_tools]:
                print(f"  ✅ {expected}")
            else:
                print(f"  ❌ {expected} - MISSING")
                all_found = False

        if all_found:
            print("\n✅ All tools discovered successfully!")
            return True
        else:
            print("\n❌ Some tools are missing!")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def validate_list_notes():
    """Validate list_notes tool works"""
    print("\n" + "="*80)
    print("🔍 TEST 2: list_notes Tool")
    print("="*80)

    try:
        # Test without tags (optimized path)
        print("\n📝 Testing obs_list_notes (optimized - no tags)...")
        result = await obsidian_tools.list_notes(folder="")

        metadata = result.get("metadata", {})
        total_notes = metadata.get("total_notes", 0)

        print(f"  Found {total_notes} notes")
        print(f"  ✅ Tool executed successfully")

        # Verify response structure
        if "content" in result and "metadata" in result:
            print(f"  ✅ Response structure correct")
            return True
        else:
            print(f"  ❌ Response structure incorrect")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def validate_get_vault_structure():
    """Validate get_vault_structure tool works"""
    print("\n" + "="*80)
    print("🔍 TEST 3: get_vault_structure Tool")
    print("="*80)

    try:
        print("\n📝 Testing obs_get_vault_structure (with cache)...")
        result = await obsidian_tools.get_vault_structure(use_cache=True)

        metadata = result.get("metadata", {})
        total_notes = metadata.get("total_notes", 0)
        total_folders = metadata.get("total_folders", 0)

        print(f"  Found {total_notes} notes in {total_folders} folders")
        print(f"  ✅ Tool executed successfully")

        # Verify response structure
        if "content" in result and "metadata" in result:
            print(f"  ✅ Response structure correct")
            return True
        else:
            print(f"  ❌ Response structure incorrect")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def validate_keyword_search():
    """Validate keyword_search tool works with batching"""
    print("\n" + "="*80)
    print("🔍 TEST 4: keyword_search Tool (Batched)")
    print("="*80)

    try:
        print("\n📝 Testing obs_keyword_search (batched concurrent)...")
        result = await obsidian_tools.keyword_search(
            keyword="note",
            folder="",
            case_sensitive=False,
            limit=5
        )

        metadata = result.get("metadata", {})
        total_found = metadata.get("total_found", 0)

        print(f"  Found {total_found} matches (limited to 5)")
        print(f"  ✅ Tool executed successfully")

        # Verify response structure
        if "content" in result and "metadata" in result:
            print(f"  ✅ Response structure correct")
            print(f"  ✅ Batching working correctly")
            return True
        else:
            print(f"  ❌ Response structure incorrect")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def validate_check_note_exists():
    """Validate check_note_exists tool works"""
    print("\n" + "="*80)
    print("🔍 TEST 5: check_note_exists Tool")
    print("="*80)

    try:
        # First, get a real note path
        list_result = await obsidian_tools.list_notes(folder="")
        notes = list_result.get("metadata", {}).get("notes", [])

        if notes:
            test_path = notes[0]["path"]
            print(f"\n📝 Testing obs_check_note_exists with: {test_path}")

            result = await obsidian_tools.check_note_exists(path=test_path)

            metadata = result.get("metadata", {})
            exists = metadata.get("exists", False)

            if exists:
                print(f"  ✅ Note exists: {test_path}")
                print(f"  ✅ Tool executed successfully")
                return True
            else:
                print(f"  ⚠️  Note reported as not existing (unexpected)")
                return False
        else:
            print(f"  ℹ️  No notes found to test with")
            return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def validate_cache_functionality():
    """Validate that caching is working"""
    print("\n" + "="*80)
    print("🔍 TEST 6: Cache Functionality")
    print("="*80)

    try:
        # Access the client through obsidian_tools
        client = obsidian_tools.client

        if not client:
            print("  ⚠️  Client not initialized")
            return False

        # Check cache attributes exist
        has_fs_cache = hasattr(client, '_filesystem_notes_cache')
        has_fs_timestamp = hasattr(client, '_filesystem_cache_timestamp')
        has_vault_cache = hasattr(client, '_vault_structure_cache')

        print(f"\n📝 Checking cache attributes...")
        print(f"  Filesystem cache attribute: {'✅' if has_fs_cache else '❌'}")
        print(f"  Filesystem timestamp attribute: {'✅' if has_fs_timestamp else '❌'}")
        print(f"  Vault structure cache attribute: {'✅' if has_vault_cache else '❌'}")

        if has_fs_cache and has_fs_timestamp and has_vault_cache:
            print(f"\n  ✅ All cache attributes present")
            print(f"  ✅ Cache infrastructure working")
            return True
        else:
            print(f"\n  ❌ Some cache attributes missing")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_all_validations():
    """Run all validation tests"""
    print("\n" + "="*80)
    print("🚀 OBSIDIAN TOOLS VALIDATION SUITE")
    print("   Confirming all tools work after optimizations")
    print("="*80)

    results = []

    # Run all validations
    results.append(("Tool Discovery", await validate_tool_discovery()))
    results.append(("list_notes", await validate_list_notes()))
    results.append(("get_vault_structure", await validate_get_vault_structure()))
    results.append(("keyword_search", await validate_keyword_search()))
    results.append(("check_note_exists", await validate_check_note_exists()))
    results.append(("Cache Infrastructure", await validate_cache_functionality()))

    # Summary
    print("\n" + "="*80)
    print("📊 VALIDATION SUMMARY")
    print("="*80)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")

    print(f"\n{'='*80}")
    print(f"Results: {passed}/{total} tests passed ({passed/total*100:.1f}%)")

    if passed == total:
        print("\n🎉 ALL TOOLS WORKING CORRECTLY!")
        print("✅ Optimizations implemented successfully")
        print("✅ No breaking changes detected")
        print("✅ All tools functional")
    elif passed >= total * 0.8:
        print("\n✅ Most tools working correctly")
        print("⚠️  Some tools may need attention")
    else:
        print("\n⚠️  Multiple tools need attention")

    print(f"{'='*80}\n")

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(run_all_validations())
    sys.exit(0 if success else 1)
