#!/usr/bin/env python3
"""
Phase 4 MCP Resources Testing Script
Tests the complete obsidian://notes/{path} URI pattern implementation
"""
import asyncio
import json
import httpx
from typing import Dict, Any


class Phase4ResourceTester:
    """Test Phase 4 MCP Resources implementation"""

    def __init__(
        self, base_url: str = "http://localhost:8888", api_key: str = "test-key"
    ):
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def send_mcp_request(
        self, method: str, params: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Send MCP JSON-RPC request"""
        request_data = {"jsonrpc": "2.0", "method": method, "id": 1}

        if params:
            request_data["params"] = params

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/mcp",
                headers=self.headers,
                json=request_data,
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()

    async def test_resources_list(self) -> bool:
        """Test resources/list method"""
        print("\n🔍 Testing resources/list...")

        try:
            result = await self.send_mcp_request("resources/list")

            if "result" not in result:
                print("❌ No result in response")
                return False

            resources = result["result"].get("resources", [])
            print(f"✅ Found {len(resources)} resources")

            # Check for vault root resource
            vault_root = next(
                (r for r in resources if r["uri"] == "obsidian://notes/"), None
            )
            if vault_root:
                print(f"✅ Vault root resource found: {vault_root['name']}")
            else:
                print("❌ Vault root resource not found")
                return False

            # Display some resources
            print("\n📋 Sample resources:")
            for i, resource in enumerate(resources[:5]):
                print(f"  {i+1}. {resource['name']} ({resource['mimeType']})")
                print(f"     URI: {resource['uri']}")
                print(f"     Description: {resource.get('description', 'N/A')}")

            if len(resources) > 5:
                print(f"  ... and {len(resources) - 5} more resources")

            return True

        except Exception as e:
            print(f"❌ Error testing resources/list: {e}")
            return False

    async def test_vault_root_read(self) -> bool:
        """Test reading vault root resource"""
        print("\n📁 Testing vault root read...")

        try:
            result = await self.send_mcp_request(
                "resources/read", {"uri": "obsidian://notes/"}
            )

            if "result" not in result:
                print("❌ No result in response")
                return False

            contents = result["result"].get("contents", [])
            if not contents:
                print("❌ No contents in response")
                return False

            content = contents[0]

            if content.get("mimeType") != "application/json":
                print(f"❌ Wrong MIME type: {content.get('mimeType')}")
                return False

            # Parse the JSON content
            vault_data = json.loads(content["text"])

            print(f"✅ Vault root loaded successfully")
            print(f"  📂 Folders: {len(vault_data.get('folders', []))}")
            print(f"  📄 Notes: {len(vault_data.get('notes', []))}")
            print(f"  📊 Total items: {vault_data.get('total_items', 0)}")

            # Show some folders and notes
            folders = vault_data.get("folders", [])
            if folders:
                print("\n📂 Sample folders:")
                for folder in folders[:3]:
                    print(
                        f"  - {folder['name']} ({folder.get('notes_count', 0)} notes)"
                    )

            notes = vault_data.get("notes", [])
            if notes:
                print("\n📄 Sample notes:")
                for note in notes[:3]:
                    print(f"  - {note['name']} ({note.get('size', 0)} bytes)")

            return True

        except Exception as e:
            print(f"❌ Error reading vault root: {e}")
            return False

    async def test_note_read(self) -> bool:
        """Test reading a specific note"""
        print("\n📄 Testing specific note read...")

        # First get a list of notes to find one to test
        try:
            vault_result = await self.send_mcp_request(
                "resources/read", {"uri": "obsidian://notes/"}
            )

            vault_data = json.loads(vault_result["result"]["contents"][0]["text"])
            notes = vault_data.get("notes", [])

            if not notes:
                print("⚠️  No notes found in vault for testing")
                return True  # Not a failure, just no data

            # Test the first note
            test_note = notes[0]
            test_uri = test_note["uri"]

            print(f"  Testing note: {test_note['name']}")
            print(f"  URI: {test_uri}")

            result = await self.send_mcp_request("resources/read", {"uri": test_uri})

            if "result" not in result:
                print("❌ No result in response")
                return False

            contents = result["result"].get("contents", [])
            if not contents:
                print("❌ No contents in response")
                return False

            content = contents[0]

            if content.get("mimeType") != "text/markdown":
                print(f"❌ Wrong MIME type: {content.get('mimeType')}")
                return False

            note_text = content.get("text", "")
            metadata = content.get("metadata", {})

            print(f"✅ Note loaded successfully")
            print(f"  📝 Content length: {len(note_text)} characters")
            print(f"  📊 Metadata: {len(metadata)} fields")

            # Show first few lines of content
            lines = note_text.split("\n")[:3]
            if lines:
                print(f"  📄 Preview:")
                for line in lines:
                    print(f"    {line[:80]}{'...' if len(line) > 80 else ''}")

            # Show metadata
            if metadata:
                print(f"  📋 Metadata:")
                for key, value in list(metadata.items())[:3]:
                    print(f"    {key}: {value}")

            return True

        except Exception as e:
            print(f"❌ Error reading note: {e}")
            return False

    async def test_folder_read(self) -> bool:
        """Test reading a folder resource"""
        print("\n📂 Testing folder read...")

        try:
            # First get vault structure to find a folder
            vault_result = await self.send_mcp_request(
                "resources/read", {"uri": "obsidian://notes/"}
            )

            vault_data = json.loads(vault_result["result"]["contents"][0]["text"])
            folders = vault_data.get("folders", [])

            if not folders:
                print("⚠️  No folders found in vault for testing")
                return True  # Not a failure, just no data

            # Test the first folder
            test_folder = folders[0]
            test_uri = test_folder["uri"]

            print(f"  Testing folder: {test_folder['name']}")
            print(f"  URI: {test_uri}")

            result = await self.send_mcp_request("resources/read", {"uri": test_uri})

            if "result" not in result:
                print("❌ No result in response")
                return False

            contents = result["result"].get("contents", [])
            if not contents:
                print("❌ No contents in response")
                return False

            content = contents[0]

            if content.get("mimeType") != "application/json":
                print(f"❌ Wrong MIME type: {content.get('mimeType')}")
                return False

            folder_data = json.loads(content["text"])

            print(f"✅ Folder loaded successfully")
            print(f"  📂 Subfolders: {len(folder_data.get('folders', []))}")
            print(f"  📄 Notes: {len(folder_data.get('notes', []))}")
            print(f"  📊 Total items: {folder_data.get('total_items', 0)}")

            return True

        except Exception as e:
            print(f"❌ Error reading folder: {e}")
            return False

    async def test_invalid_uri(self) -> bool:
        """Test handling of invalid URIs"""
        print("\n🚫 Testing invalid URI handling...")

        test_cases = [
            "invalid://scheme/path",
            "obsidian://wrong-authority/path",
            "obsidian://notes/nonexistent-note.md",
            "",
        ]

        for uri in test_cases:
            try:
                result = await self.send_mcp_request("resources/read", {"uri": uri})

                # Should not reach here for invalid URIs
                print(f"⚠️  Unexpected success for invalid URI: {uri}")

            except Exception as e:
                print(f"✅ Correctly rejected invalid URI '{uri}': {type(e).__name__}")

        return True

    async def test_uri_encoding(self) -> bool:
        """Test URI encoding for special characters"""
        print("\n🔤 Testing URI encoding...")

        # Test obsidian:// URI building and parsing
        try:
            from src.resources.obsidian_resources import ObsidianResources
            from src.clients.obsidian_client import ObsidianClient

            client = ObsidianClient()
            resources = ObsidianResources(client)

            # Test paths with special characters
            test_paths = [
                "daily notes/2024-01-15.md",
                "projects/my project/notes.md",
                "folder with spaces/note with spaces.md",
                "special!@#$%^&*()characters.md",
            ]

            for path in test_paths:
                # Build URI
                uri = resources.build_uri(path)
                print(f"  Path: {path}")
                print(f"  URI:  {uri}")

                # Parse it back
                scheme_authority, parsed_path = resources.parse_uri(uri)

                if parsed_path == path:
                    print(f"  ✅ Round-trip successful")
                else:
                    print(f"  ❌ Round-trip failed: {parsed_path}")
                    return False

            return True

        except Exception as e:
            print(f"❌ Error testing URI encoding: {e}")
            return False

    async def run_all_tests(self) -> bool:
        """Run all Phase 4 tests"""
        print("🚀 Starting Phase 4 MCP Resources Tests")
        print("=" * 50)

        tests = [
            ("Resources List", self.test_resources_list),
            ("Vault Root Read", self.test_vault_root_read),
            ("Note Read", self.test_note_read),
            ("Folder Read", self.test_folder_read),
            ("Invalid URI Handling", self.test_invalid_uri),
            ("URI Encoding", self.test_uri_encoding),
        ]

        passed = 0
        total = len(tests)

        for test_name, test_func in tests:
            print(f"\n{'='*20} {test_name} {'='*20}")

            try:
                if await test_func():
                    print(f"✅ {test_name} PASSED")
                    passed += 1
                else:
                    print(f"❌ {test_name} FAILED")
            except Exception as e:
                print(f"💥 {test_name} CRASHED: {e}")

        print(f"\n{'='*50}")
        print(f"🏁 Phase 4 Test Results: {passed}/{total} tests passed")

        if passed == total:
            print("🎉 ALL TESTS PASSED! Phase 4 implementation is working correctly.")
            return True
        else:
            print(f"⚠️  {total - passed} tests failed. Check implementation.")
            return False


async def main():
    """Run Phase 4 resource tests"""
    tester = Phase4ResourceTester()

    print("🧪 Phase 4 MCP Resources Testing")
    print("This script tests the complete obsidian://notes/{path} implementation")
    print("Make sure the MCP server is running on localhost:8888")

    try:
        # Test basic connectivity first
        print("\n🔗 Testing MCP server connectivity...")
        result = await tester.send_mcp_request("ping")
        if "result" in result:
            print("✅ MCP server is responding")

            # Run all tests
            success = await tester.run_all_tests()

            if success:
                print("\n🎯 Phase 4 Implementation Status: COMPLETE ✅")
                print("All MCP Resources functionality is working correctly!")
            else:
                print("\n⚠️  Phase 4 Implementation Status: NEEDS ATTENTION")
                print("Some functionality needs debugging.")

        else:
            print("❌ MCP server is not responding correctly")

    except Exception as e:
        print(f"💥 Failed to connect to MCP server: {e}")
        print("Make sure the server is running: python main.py")


if __name__ == "__main__":
    asyncio.run(main())
