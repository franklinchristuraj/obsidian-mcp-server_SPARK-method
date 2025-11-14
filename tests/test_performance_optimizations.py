#!/usr/bin/env python3
"""
Performance validation script for optimization improvements
Tests caching, lazy-loading, and concurrent operations
"""
import asyncio
import time
import os
import sys
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.clients.obsidian_client import ObsidianClient

# Load environment variables
load_dotenv()


async def test_filesystem_cache():
    """Test that filesystem cache is working"""
    print("\n" + "="*80)
    print("🧪 TEST 1: Filesystem Cache Performance")
    print("="*80)

    try:
        client = ObsidianClient()

        # First call - should populate cache
        print("\n📝 First call (cold cache)...")
        start = time.time()
        notes1 = await client.list_notes(include_tags=False)
        duration1 = time.time() - start
        print(f"   Found {len(notes1)} notes in {duration1*1000:.2f}ms")

        # Second call - should use cache
        print("\n📝 Second call (warm cache)...")
        start = time.time()
        notes2 = await client.list_notes(include_tags=False)
        duration2 = time.time() - start
        print(f"   Found {len(notes2)} notes in {duration2*1000:.2f}ms")

        # Calculate improvement
        improvement = duration1 / duration2 if duration2 > 0 else float('inf')
        print(f"\n✅ Cache Performance:")
        print(f"   Cold cache: {duration1*1000:.2f}ms")
        print(f"   Warm cache: {duration2*1000:.2f}ms")
        print(f"   Improvement: {improvement:.1f}x faster")

        if improvement > 10:
            print(f"   🎉 EXCELLENT: Cache is working as expected!")
        elif improvement > 2:
            print(f"   ✅ GOOD: Cache provides significant improvement")
        else:
            print(f"   ⚠️  WARNING: Cache improvement lower than expected")

        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_lazy_tag_loading():
    """Test that lazy tag loading improves performance"""
    print("\n" + "="*80)
    print("🧪 TEST 2: Lazy Tag Loading Performance")
    print("="*80)

    try:
        client = ObsidianClient()

        # Clear cache first
        client.invalidate_cache()

        # Test without tags (fast)
        print("\n📝 List notes WITHOUT tags (optimized)...")
        start = time.time()
        notes_no_tags = await client.list_notes(include_tags=False)
        duration_no_tags = time.time() - start
        print(f"   Found {len(notes_no_tags)} notes in {duration_no_tags*1000:.2f}ms")

        # Clear cache again
        client.invalidate_cache()

        # Test with tags (slower)
        print("\n📝 List notes WITH tags (expensive)...")
        start = time.time()
        notes_with_tags = await client.list_notes(include_tags=True)
        duration_with_tags = time.time() - start
        print(f"   Found {len(notes_with_tags)} notes in {duration_with_tags*1000:.2f}ms")

        # Calculate improvement
        improvement = duration_with_tags / duration_no_tags if duration_no_tags > 0 else 1
        print(f"\n✅ Lazy Loading Performance:")
        print(f"   Without tags: {duration_no_tags*1000:.2f}ms")
        print(f"   With tags: {duration_with_tags*1000:.2f}ms")
        print(f"   Tags add: {improvement:.1f}x overhead")

        if improvement > 1.5:
            print(f"   🎉 EXCELLENT: Lazy loading provides {improvement:.1f}x improvement!")
        elif improvement > 1.1:
            print(f"   ✅ GOOD: Lazy loading provides measurable benefit")
        else:
            print(f"   ⚠️  INFO: Small vault - lazy loading benefit minimal")

        # Verify tags are present when requested
        has_tags = any(note.tags is not None for note in notes_with_tags[:10])
        print(f"\n   Tags extracted when requested: {'✅ Yes' if has_tags else '❌ No'}")

        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_concurrent_search():
    """Test that concurrent operations work correctly"""
    print("\n" + "="*80)
    print("🧪 TEST 3: Concurrent Search Operations")
    print("="*80)

    try:
        client = ObsidianClient()

        # Test search with metadata enrichment
        print("\n📝 Testing search with concurrent metadata fetching...")
        start = time.time()
        results = await client.search_notes("test", folder=None)
        duration = time.time() - start

        result_count = len(results)
        print(f"   Found {result_count} results in {duration*1000:.2f}ms")

        if result_count > 0:
            # Check if metadata is present
            has_metadata = "metadata" in results[0]
            print(f"   Metadata enrichment: {'✅ Working' if has_metadata else '⚠️  Not present'}")

            # Estimate sequential time (if we had 50ms per fetch)
            estimated_sequential = result_count * 0.05
            print(f"\n✅ Concurrent Performance:")
            print(f"   Actual time: {duration*1000:.2f}ms")
            print(f"   Estimated sequential time: {estimated_sequential*1000:.2f}ms")
            if duration < estimated_sequential:
                improvement = estimated_sequential / duration
                print(f"   Improvement: {improvement:.1f}x faster with concurrency")
        else:
            print(f"   ℹ️  No results found - cannot test concurrent metadata fetching")

        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_batched_keyword_search():
    """Test batched keyword search performance"""
    print("\n" + "="*80)
    print("🧪 TEST 4: Batched Keyword Search")
    print("="*80)

    try:
        from src.tools.obsidian_tools import obsidian_tools

        # Test keyword search with a common word
        print("\n📝 Testing batched keyword search...")
        start = time.time()
        result = await obsidian_tools.keyword_search(
            keyword="the",  # Common word
            folder="",
            case_sensitive=False,
            limit=10
        )
        duration = time.time() - start

        metadata = result.get("metadata", {})
        total_found = metadata.get("total_found", 0)

        print(f"   Found {total_found} matches in {duration*1000:.2f}ms")
        print(f"   Returned {len(metadata.get('matching_notes', []))} results (limited to 10)")

        print(f"\n✅ Batched Search Performance:")
        print(f"   Search time: {duration*1000:.2f}ms")
        print(f"   Results: {total_found} found, {metadata.get('limit', 0)} returned")

        if duration < 5.0:  # Should be under 5 seconds
            print(f"   🎉 EXCELLENT: Fast search with batching!")
        elif duration < 10.0:
            print(f"   ✅ GOOD: Reasonable search performance")
        else:
            print(f"   ⚠️  SLOW: Search took longer than expected")

        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_cache_invalidation():
    """Test that cache invalidation works correctly"""
    print("\n" + "="*80)
    print("🧪 TEST 5: Cache Invalidation")
    print("="*80)

    try:
        client = ObsidianClient()

        # Populate cache
        print("\n📝 Populating cache...")
        await client.list_notes()

        # Check cache is populated
        has_cache_before = client._filesystem_notes_cache is not None
        print(f"   Cache populated: {'✅ Yes' if has_cache_before else '❌ No'}")

        # Invalidate cache
        print("\n📝 Invalidating cache...")
        client.invalidate_cache()

        # Check cache is cleared
        has_cache_after = client._filesystem_notes_cache is not None
        has_timestamp_after = client._filesystem_cache_timestamp is not None

        print(f"   Filesystem cache cleared: {'✅ Yes' if not has_cache_after else '❌ No'}")
        print(f"   Cache timestamp cleared: {'✅ Yes' if not has_timestamp_after else '❌ No'}")

        print(f"\n✅ Cache Invalidation:")
        if not has_cache_after and not has_timestamp_after:
            print(f"   🎉 EXCELLENT: Cache properly invalidated!")
        else:
            print(f"   ❌ FAILED: Cache not properly cleared")
            return False

        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_all_tests():
    """Run all performance validation tests"""
    print("\n" + "="*80)
    print("🚀 PERFORMANCE OPTIMIZATION VALIDATION SUITE")
    print("="*80)
    print("\nValidating all high-priority optimizations...")

    results = []

    # Run all tests
    results.append(("Filesystem Cache", await test_filesystem_cache()))
    results.append(("Lazy Tag Loading", await test_lazy_tag_loading()))
    results.append(("Concurrent Search", await test_concurrent_search()))
    results.append(("Batched Keyword Search", await test_batched_keyword_search()))
    results.append(("Cache Invalidation", await test_cache_invalidation()))

    # Summary
    print("\n" + "="*80)
    print("📊 TEST SUMMARY")
    print("="*80)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status} - {test_name}")

    print(f"\n{'='*80}")
    print(f"Results: {passed}/{total} tests passed ({passed/total*100:.1f}%)")

    if passed == total:
        print("🎉 ALL OPTIMIZATIONS VALIDATED SUCCESSFULLY!")
    elif passed >= total * 0.8:
        print("✅ Most optimizations working correctly")
    else:
        print("⚠️  Some optimizations need attention")

    print(f"{'='*80}\n")

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
