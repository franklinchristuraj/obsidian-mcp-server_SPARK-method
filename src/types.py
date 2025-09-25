"""
MCP Data Types and Structures
Shared types to avoid circular imports
"""
from dataclasses import dataclass
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum


class MCPMessageType(Enum):
    """MCP message types for proper protocol handling"""

    INITIALIZE = "initialize"
    TOOLS_LIST = "tools/list"
    TOOLS_CALL = "tools/call"
    RESOURCES_LIST = "resources/list"
    RESOURCES_READ = "resources/read"
    PROMPTS_LIST = "prompts/list"
    PROMPTS_GET = "prompts/get"
    PING = "ping"
    # Notifications
    NOTIFICATIONS_INITIALIZED = "notifications/initialized"


@dataclass
class MCPTool:
    """MCP Tool definition"""

    name: str
    description: str
    inputSchema: Dict[str, Any]


@dataclass
class MCPResource:
    """MCP Resource definition"""

    uri: str
    name: str
    description: Optional[str] = None
    mimeType: Optional[str] = None


@dataclass
class MCPPrompt:
    """MCP Prompt definition"""

    name: str
    description: str
    arguments: List[Dict[str, Any]] = None

    def __post_init__(self):
        if self.arguments is None:
            self.arguments = []


@dataclass
class MCPCapabilities:
    """MCP Server capabilities"""

    tools: Dict[str, Any] = None
    resources: Dict[str, Any] = None
    prompts: Dict[str, Any] = None
    logging: Dict[str, Any] = None

    def __post_init__(self):
        if self.tools is None:
            self.tools = {}
        if self.resources is None:
            self.resources = {}
        if self.prompts is None:
            self.prompts = {}
        if self.logging is None:
            self.logging = {}
