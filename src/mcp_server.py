"""
MCP Protocol Server Implementation
Handles Model Context Protocol with SSE streaming support
"""
import json
import asyncio
import time
from typing import Dict, Any, Optional, List, AsyncGenerator
from .types import MCPMessageType, MCPTool, MCPResource, MCPCapabilities, MCPPrompt


class MCPProtocolHandler:
    """
    Handles MCP protocol operations with streaming support
    """

    def __init__(self):
        self.session_id: Optional[str] = None
        self.session_initialized: bool = False
        self.protocol_version = "2024-11-05"
        self.server_info = {"name": "obsidian-mcp-server", "version": "1.0.0"}
        self.capabilities = MCPCapabilities(
            tools={"listChanged": True},
            resources={"subscribe": True, "listChanged": True},
            prompts={"listChanged": True},
            logging={},
        )

        # Register available tools from obsidian_tools
        self.tools: List[MCPTool] = [
            MCPTool(
                name="ping",
                description="Test connectivity to the MCP server",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            )
        ]

        # Add all Obsidian tools (import here to avoid circular import)
        try:
            from .tools.obsidian_tools import obsidian_tools

            self.tools.extend(obsidian_tools.get_tools())
        except Exception as e:
            print(f"Warning: Could not load Obsidian tools: {e}")

        # Register available resources (loaded dynamically in Phase 4)
        self.resources: List[MCPResource] = []
        self._resources_loaded = False

        # Register available prompts
        self.prompts: List[MCPPrompt] = []
        try:
            from .prompts.obsidian_prompts import obsidian_prompts

            self.prompts.extend(obsidian_prompts.get_prompts())
        except Exception as e:
            print(f"Warning: Could not load Obsidian prompts: {e}")

    async def handle_request(
        self, method: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Handle MCP protocol requests
        Returns either immediate response or streaming generator
        """
        try:
            if method == MCPMessageType.INITIALIZE.value:
                return await self._handle_initialize(params)
            elif method == MCPMessageType.PING.value:
                return await self._handle_ping(params)
            elif method == MCPMessageType.TOOLS_LIST.value:
                return await self._handle_tools_list(params)
            elif method == MCPMessageType.TOOLS_CALL.value:
                return await self._handle_tools_call(params)
            elif method == MCPMessageType.RESOURCES_LIST.value:
                return await self._handle_resources_list(params)
            elif method == MCPMessageType.RESOURCES_READ.value:
                return await self._handle_resources_read(params)
            elif method == MCPMessageType.PROMPTS_LIST.value:
                return await self._handle_prompts_list(params)
            elif method == MCPMessageType.PROMPTS_GET.value:
                return await self._handle_prompts_get(params)
            elif method == MCPMessageType.NOTIFICATIONS_INITIALIZED.value:
                return await self._handle_notifications_initialized(params)
            else:
                raise ValueError(f"Method not found: {method}")

        except Exception as e:
            raise Exception(f"Error handling {method}: {str(e)}")

    async def _handle_initialize(
        self, params: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Handle MCP initialization"""
        if params:
            client_info = params.get("clientInfo", {})
            requested_version = params.get("protocolVersion")

            # Validate protocol version compatibility
            if requested_version and requested_version != self.protocol_version:
                # For now, accept any version but note the difference
                pass

        return {
            "protocolVersion": self.protocol_version,
            "capabilities": {
                "tools": self.capabilities.tools,
                "resources": self.capabilities.resources,
                "prompts": self.capabilities.prompts,
                "logging": self.capabilities.logging,
            },
            "serverInfo": self.server_info,
        }

    async def _handle_ping(self, params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Handle ping request"""
        return {
            "message": "pong",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "serverInfo": self.server_info,
        }

    async def _handle_tools_list(
        self, params: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """List available tools"""
        return {
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.inputSchema,
                }
                for tool in self.tools
            ]
        }

    async def _handle_tools_call(
        self, params: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Execute a tool call"""
        if not params:
            raise ValueError("Missing parameters for tool call")

        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if not tool_name:
            raise ValueError("Missing tool name")

        # Find the tool
        tool = next((t for t in self.tools if t.name == tool_name), None)
        if not tool:
            raise ValueError(f"Tool not found: {tool_name}")

        # Execute the tool
        if tool_name == "ping":
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Pong! Tool called successfully at {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
                    }
                ]
            }

        # Execute Obsidian tools
        try:
            from .tools.obsidian_tools import obsidian_tools

            return await obsidian_tools.execute_tool(tool_name, arguments)
        except Exception as e:
            # If obsidian tool fails, provide a helpful error
            return {
                "content": [
                    {"type": "text", "text": f"❌ Tool '{tool_name}' failed: {str(e)}"}
                ]
            }

    async def _handle_resources_list(
        self, params: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """List available resources"""
        # Load resources dynamically from vault
        await self._ensure_resources_loaded()

        return {
            "resources": [
                {
                    "uri": resource.uri,
                    "name": resource.name,
                    "description": resource.description,
                    "mimeType": resource.mimeType,
                }
                for resource in self.resources
            ]
        }

    async def _handle_resources_read(
        self, params: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Read a specific resource"""
        if not params:
            raise ValueError("Missing parameters for resource read")

        uri = params.get("uri")
        if not uri:
            raise ValueError("Missing resource URI")

        try:
            # Use ObsidianResources to read the content
            from .resources.obsidian_resources import get_obsidian_resources

            resources_handler = get_obsidian_resources()
            content = await resources_handler.read_resource(uri)

            result = {
                "contents": [
                    {
                        "uri": content.uri,
                        "mimeType": content.mimeType,
                    }
                ]
            }

            # Add text or blob content
            if content.text is not None:
                result["contents"][0]["text"] = content.text
            elif content.blob is not None:
                result["contents"][0]["blob"] = content.blob

            # Add metadata if available
            if content.metadata:
                result["contents"][0]["metadata"] = content.metadata

            return result

        except Exception as e:
            # If ObsidianResources fails, provide a helpful error
            raise ValueError(f"Failed to read resource {uri}: {str(e)}")

    def add_tool(self, tool: MCPTool):
        """Add a new tool to the server"""
        self.tools.append(tool)

    def add_resource(self, resource: MCPResource):
        """Add a new resource to the server"""
        self.resources.append(resource)

    async def _ensure_resources_loaded(self):
        """Ensure resources are loaded from ObsidianResources"""
        if self._resources_loaded:
            return

        try:
            from .resources.obsidian_resources import get_obsidian_resources

            resources_handler = get_obsidian_resources()
            discovered_resources = await resources_handler.discover_resources()

            # Replace current resources with discovered ones
            self.resources = discovered_resources
            self._resources_loaded = True

        except Exception as e:
            print(f"Warning: Could not load resources: {e}")
            # Keep empty resources list if loading fails
            self._resources_loaded = True  # Don't keep retrying

    def invalidate_resources_cache(self):
        """Force reload of resources on next request"""
        self._resources_loaded = False

        # Also invalidate the ObsidianResources cache
        try:
            from .resources.obsidian_resources import get_obsidian_resources

            resources_handler = get_obsidian_resources()
            resources_handler.invalidate_cache()
        except Exception:
            pass  # Ignore if resources not available

    async def create_streaming_response(
        self, data: Any, chunk_size: int = 1024
    ) -> AsyncGenerator[str, None]:
        """
        Create a streaming response for large data
        This will be used for large note content, search results, etc.
        """
        if isinstance(data, str):
            # Stream text content in chunks
            content = data
            for i in range(0, len(content), chunk_size):
                chunk = content[i : i + chunk_size]
                sse_data = {
                    "type": "content",
                    "chunk": chunk,
                    "isComplete": i + chunk_size >= len(content),
                }
                yield f"data: {json.dumps(sse_data)}\n\n"
                # Small delay to simulate streaming and prevent overwhelming
                await asyncio.sleep(0.01)

        elif isinstance(data, dict):
            # Stream JSON data
            json_str = json.dumps(data, indent=2)
            async for chunk in self.create_streaming_response(json_str, chunk_size):
                yield chunk

        elif isinstance(data, list):
            # Stream list items one by one
            for i, item in enumerate(data):
                sse_data = {
                    "type": "list_item",
                    "item": item,
                    "index": i,
                    "isComplete": i == len(data) - 1,
                }
                yield f"data: {json.dumps(sse_data)}\n\n"
                await asyncio.sleep(0.01)

        # Send completion marker
        completion_data = {"type": "complete", "message": "Streaming complete"}
        yield f"data: {json.dumps(completion_data)}\n\n"

    async def _handle_prompts_list(
        self, params: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """List all available prompts"""
        prompt_list = []
        for prompt in self.prompts:
            prompt_dict = {
                "name": prompt.name,
                "description": prompt.description,
            }
            if prompt.arguments:
                prompt_dict["arguments"] = prompt.arguments
            prompt_list.append(prompt_dict)

        return {"prompts": prompt_list}

    async def _handle_prompts_get(
        self, params: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Get a specific prompt's content"""
        if not params:
            raise ValueError("Missing parameters for prompt get")

        name = params.get("name")
        if not name:
            raise ValueError("Missing prompt name")

        arguments = params.get("arguments", {})

        try:
            from .prompts.obsidian_prompts import obsidian_prompts

            content = await obsidian_prompts.get_prompt_content(name, arguments)

            return {
                "description": f"Template and formatting instructions for {name}",
                "messages": [
                    {
                        "role": "user",
                        "content": {
                            "type": "text",
                            "text": content,
                        },
                    }
                ],
            }
        except Exception as e:
            raise ValueError(f"Failed to get prompt {name}: {str(e)}")

    async def _handle_notifications_initialized(
        self, params: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Handle MCP notifications/initialized notification
        This is sent by clients after successful initialization
        """
        # For notifications, MCP specification requires no response (null response)
        # But we can internally track the initialization state
        self.session_initialized = True
        return None

    def invalidate_resources_cache(self):
        """Invalidate resources cache to force reload"""
        self._resources_loaded = False
        self.resources = []


# Global MCP handler instance
mcp_handler = MCPProtocolHandler()
