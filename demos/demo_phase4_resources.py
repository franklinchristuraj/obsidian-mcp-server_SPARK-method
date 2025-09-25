#!/usr/bin/env python3
"""
Phase 4 MCP Resources Demo
Demonstrates the obsidian://notes/{path} URI pattern functionality
"""
import asyncio
import json
import httpx
from typing import Dict, Any


async def demo_mcp_resources():
    """Demonstrate Phase 4 MCP Resources functionality"""

    print("🚀 Phase 4 MCP Resources Demo")
    print("=" * 50)
    print("Demonstrating browseable vault structure via obsidian://notes/{path}")

    base_url = "http://localhost:8888"
    headers = {"Authorization": "Bearer test-key", "Content-Type": "application/json"}

    async def send_request(method: str, params: Dict[str, Any] = None):
        """Send MCP request"""
        request_data = {"jsonrpc": "2.0", "method": method, "id": 1}
        if params:
            request_data["params"] = params

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{base_url}/mcp", headers=headers, json=request_data, timeout=30.0
            )
            response.raise_for_status()
            return response.json()

    try:
        # 1. List all available resources
        print("\n📋 Step 1: Listing all available resources")
        print("-" * 40)

        result = await send_request("resources/list")
        resources = result["result"]["resources"]

        print(f"Found {len(resources)} resources:")
        for i, resource in enumerate(resources[:10], 1):
            print(f"  {i:2d}. {resource['name']} ({resource['mimeType']})")
            print(f"      URI: {resource['uri']}")
            print(f"      Description: {resource.get('description', 'N/A')}")

        if len(resources) > 10:
            print(f"      ... and {len(resources) - 10} more resources")

        # 2. Browse vault root
        print("\n📁 Step 2: Browsing vault root (obsidian://notes/)")
        print("-" * 40)

        result = await send_request("resources/read", {"uri": "obsidian://notes/"})
        vault_content = json.loads(result["result"]["contents"][0]["text"])

        print(f"Vault structure:")
        print(f"  📂 Folders: {len(vault_content.get('folders', []))}")
        print(f"  📄 Notes: {len(vault_content.get('notes', []))}")
        print(f"  📊 Total items: {vault_content.get('total_items', 0)}")

        # Show folders
        folders = vault_content.get("folders", [])
        if folders:
            print(f"\n📂 Folders in vault root:")
            for folder in folders[:5]:
                print(
                    f"  - {folder['name']} ({folder.get('notes_count', 0)} notes, {folder.get('subfolders_count', 0)} subfolders)"
                )
                print(f"    URI: {folder['uri']}")

        # Show notes
        notes = vault_content.get("notes", [])
        if notes:
            print(f"\n📄 Notes in vault root:")
            for note in notes[:5]:
                print(f"  - {note['name']} ({note.get('size', 0)} bytes)")
                print(f"    URI: {note['uri']}")
                if note.get("tags"):
                    print(f"    Tags: {', '.join(note['tags'])}")

        # 3. Browse a specific folder (if available)
        if folders:
            print(f"\n📂 Step 3: Browsing folder '{folders[0]['name']}'")
            print("-" * 40)

            folder_uri = folders[0]["uri"]
            result = await send_request("resources/read", {"uri": folder_uri})
            folder_content = json.loads(result["result"]["contents"][0]["text"])

            print(f"Folder '{folders[0]['name']}' contents:")
            print(f"  📂 Subfolders: {len(folder_content.get('folders', []))}")
            print(f"  📄 Notes: {len(folder_content.get('notes', []))}")

            # Show folder contents
            folder_notes = folder_content.get("notes", [])
            if folder_notes:
                print(f"\n📄 Notes in this folder:")
                for note in folder_notes[:3]:
                    print(f"  - {note['name']} ({note.get('size', 0)} bytes)")

        # 4. Read a specific note (if available)
        all_notes = notes + [
            note for folder in folders for note in vault_content.get("notes", [])
        ]
        if vault_content.get("notes"):
            test_note = vault_content["notes"][0]

            print(f"\n📄 Step 4: Reading note '{test_note['name']}'")
            print("-" * 40)

            result = await send_request("resources/read", {"uri": test_note["uri"]})
            note_content = result["result"]["contents"][0]

            print(f"Note: {test_note['name']}")
            print(f"MIME Type: {note_content['mimeType']}")
            print(f"Content length: {len(note_content['text'])} characters")

            # Show metadata
            metadata = note_content.get("metadata", {})
            if metadata:
                print(f"\nMetadata:")
                for key, value in metadata.items():
                    if key != "content_length":
                        print(f"  {key}: {value}")

            # Show content preview
            content_lines = note_content["text"].split("\n")
            print(f"\nContent preview (first 5 lines):")
            for i, line in enumerate(content_lines[:5], 1):
                preview = line[:80] + "..." if len(line) > 80 else line
                print(f"  {i:2d}: {preview}")

            if len(content_lines) > 5:
                print(f"  ... and {len(content_lines) - 5} more lines")

        # 5. Demonstrate URI encoding
        print(f"\n🔤 Step 5: URI Pattern Demonstration")
        print("-" * 40)

        print("URI Pattern: obsidian://notes/{path}")
        print("Examples from discovered resources:")

        example_uris = [
            "obsidian://notes/",
            "obsidian://notes/daily/",
            "obsidian://notes/projects/my-project.md",
        ]

        # Show real URIs from resources
        for resource in resources[:5]:
            if resource["uri"].startswith("obsidian://notes/"):
                path = resource["uri"][len("obsidian://notes/") :]
                print(f"  Path: '{path}' → URI: {resource['uri']}")

        print(f"\n✅ Phase 4 Demo Complete!")
        print("=" * 50)
        print("Key Features Demonstrated:")
        print("  ✅ Dynamic resource discovery from vault structure")
        print("  ✅ obsidian://notes/{path} URI pattern")
        print("  ✅ Folder browsing (application/json)")
        print("  ✅ Note reading (text/markdown)")
        print("  ✅ Rich metadata (size, dates, tags)")
        print("  ✅ Hierarchical vault structure navigation")

    except Exception as e:
        print(f"❌ Demo failed: {e}")
        print("Make sure the MCP server is running: python main.py")


if __name__ == "__main__":
    asyncio.run(demo_mcp_resources())
