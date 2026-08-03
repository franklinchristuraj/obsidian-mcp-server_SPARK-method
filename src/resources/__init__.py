"""
MCP Resources Implementation
Provides browseable vault structure via obsidian://notes/{path} URI patterns
"""

from .obsidian_resources import (
    CURATED_ROOT_PINS,
    UI_MIME_TYPE,
    ObsidianResources,
    ResourceContent,
    get_obsidian_resources,
)

__all__ = [
    "CURATED_ROOT_PINS",
    "UI_MIME_TYPE",
    "ObsidianResources",
    "ResourceContent",
    "get_obsidian_resources",
]
