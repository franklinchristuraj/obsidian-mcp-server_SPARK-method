"""
MCP Resources Implementation
Provides browseable vault structure via obsidian://notes/{path} URI patterns
"""

from .obsidian_resources import (
    ObsidianResources,
    ResourceContent,
    get_obsidian_resources,
)

__all__ = ["ObsidianResources", "ResourceContent", "get_obsidian_resources"]
