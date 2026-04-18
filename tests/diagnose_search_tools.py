#!/usr/bin/env python3
"""
Diagnostic script for search-related code paths (client + keyword search).
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from src.tools.obsidian_tools import obsidian_tools

load_dotenv()


async def test_keyword_search():
    """Exercise keyword_search (MCP tool name: search)."""
    print("\n" + "=" * 80)
    print("🔍 Testing search (keyword_search implementation)")
    print("=" * 80)

    if not obsidian_tools.client:
        print("❌ Client not initialized - need OBSIDIAN_API_KEY")
        return False

    try:
        print("\n📝 Calling keyword_search with keyword 'note'...")
        result = await obsidian_tools.keyword_search(
            keyword="note",
            folder="",
            case_sensitive=False,
            limit=5,
        )

        print("✅ Search completed successfully")
        print(f"Result type: {type(result)}")
        print(f"Result keys: {result.keys() if isinstance(result, dict) else 'N/A'}")

        if isinstance(result, dict):
            metadata = result.get("metadata", {})
            print(f"Total found: {metadata.get('total_found', 0)}")
            print(f"Keyword: {metadata.get('keyword', 'N/A')}")
            print(f"Limit: {metadata.get('limit', 0)}")

        return True

    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_client_search_notes():
    """Test the underlying client search_notes method."""
    print("\n" + "=" * 80)
    print("🔍 Testing ObsidianClient.search_notes (underlying method)")
    print("=" * 80)

    if not obsidian_tools.client:
        print("❌ Client not initialized - need OBSIDIAN_API_KEY")
        return False

    try:
        print("\n📝 Calling client.search_notes directly...")
        results = await obsidian_tools.client.search_notes("test")

        print("✅ Client search completed")
        print(f"Results type: {type(results)}")
        print(
            f"Number of results: {len(results) if isinstance(results, list) else 'N/A'}"
        )

        if isinstance(results, list) and len(results) > 0:
            print(f"First result keys: {results[0].keys()}")
            print(f"Has metadata: {'metadata' in results[0]}")

        return True

    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_list_notes():
    """Test list_notes to ensure it works."""
    print("\n" + "=" * 80)
    print("🔍 Testing list_notes (dependency of keyword_search)")
    print("=" * 80)

    if not obsidian_tools.client:
        print("❌ Client not initialized - need OBSIDIAN_API_KEY")
        return False

    try:
        print("\n📝 Calling list_notes...")
        notes = await obsidian_tools.client.list_notes(folder=None, include_tags=False)

        print("✅ List notes completed")
        print(f"Number of notes: {len(notes)}")

        if notes and len(notes) > 0:
            print(f"First note: {notes[0].path}")
            print(f"Has tags: {notes[0].tags is not None}")

        return True

    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
        return False


async def run_diagnostics():
    """Run all diagnostic tests."""
    print("\n" + "=" * 80)
    print("🔬 SEARCH TOOLS DIAGNOSTIC SUITE")
    print("=" * 80)

    results = []

    results.append(("list_notes", await test_list_notes()))
    results.append(("client.search_notes", await test_client_search_notes()))
    results.append(("search (keyword_search)", await test_keyword_search()))

    print("\n" + "=" * 80)
    print("📊 DIAGNOSTIC SUMMARY")
    print("=" * 80)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")

    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_diagnostics())
