"""
MCP Protocol Server Implementation
Handles Model Context Protocol with SSE streaming support
"""
import copy
import json
import asyncio
import time
from typing import Dict, Any, Optional, List, AsyncGenerator, Tuple
from .types import MCPMessageType, MCPTool, MCPResource, MCPCapabilities, MCPPrompt
from .request_context import request_meta
from .scope import workspace_ctx

# prompts/get "description" must match each prompt (not a generic template blurb)
_PROMPTS_GET_DESCRIPTIONS: Dict[str, str] = {
    "vault_mcp_agent_guide": (
        "Canonical guide: workspaces, all MCP tools (including vault intelligence), "
        "scope/paths, entity graph conventions—load this first every session."
    ),
    "note_template_system": (
        "SPARK-style folders and YAML templates; paths are under a workspace "
        "(personal/passion/work/parallax) when using MCP tools—pair with vault_mcp_agent_guide."
    ),
    "daily_note_template": (
        "Daily note YAML and sections; MCP path is e.g. 06_daily-notes/YYYY-MM-DD.md "
        "plus scope=personal (or allowed workspace)."
    ),
    "project_note_template": (
        "Project note YAML under 02_projects/; set MCP scope to the workspace that owns the project."
    ),
    "area_note_template": (
        "Area note YAML under 03_areas/; choose MCP scope "
        "(personal/passion/work/parallax) from context."
    ),
    "format_preservation_rules": (
        "YAML and structure preservation when editing via MCP; paths remain workspace-relative."
    ),
}


class MCPProtocolHandler:
    """
    Handles MCP protocol operations with streaming support
    """

    # Protocol versions this server understands, newest first. The first
    # entry is offered to clients that don't request a specific version.
    SUPPORTED_PROTOCOL_VERSIONS = (
        "2026-07-28",
        "2025-06-18",
        "2025-03-26",
        "2024-11-05",
    )

    # Page sizes for cursor pagination (spec 2025-06-18). Tools page size is
    # set well above the current tool count so today's non-paginating clients
    # keep getting the full list in one response. Resources list workspace
    # roots + pins only (~4–8 items); page size still chunks if that grows.
    TOOLS_PAGE_SIZE = 200
    RESOURCES_PAGE_SIZE = 200

    # SEP-2549 cache hints (ttlMs / cacheScope)
    TOOLS_LIST_TTL_MS = 300_000
    PROMPTS_LIST_TTL_MS = 300_000
    RESOURCES_LIST_TTL_MS = 60_000
    RESOURCES_READ_TTL_MS = 300_000

    def __init__(self):
        self.session_id: Optional[str] = None
        self.session_initialized: bool = False
        self.protocol_version = self.SUPPORTED_PROTOCOL_VERSIONS[0]
        self.server_info = {
            "name": "obsidian-mcp-server",
            "version": "2.1.0",
            "description": (
                "Obsidian MCP server (v2.1.0): workspace-scoped CRUD "
                "(personal / passion / work / parallax), vault intelligence, capture inbox, "
                "create_event/create_engagement (work-only), impact snapshots, "
                "and MCP Apps (prep_card, lint_queue, snapshot_grid, debrief_form, triage_board, "
                "promote_capture). Load MCP prompt vault_mcp_agent_guide first."
            ),
        }
        self.instructions = (
            "Obsidian vault MCP server. Before doing vault work, fetch the "
            "'vault_mcp_agent_guide' prompt (prompts/get) - it covers workspaces "
            "(personal/passion/work/parallax), write_scopes, the entity graph tools "
            "(resolve_entity, get_dossier, build_context, graph/timeline tools), and "
            "path/scope conventions. Call 'workspaces' first to see which scopes this "
            "API key can read and write."
        )
        self.capabilities = MCPCapabilities(
            tools={"listChanged": False},
            resources={"subscribe": False, "listChanged": False},
            prompts={"listChanged": False},
            logging={},
            completions={},
            extensions={
                # SEP-1865 MCP Apps
                "io.modelcontextprotocol/ui": {
                    "mimeTypes": ["text/html;profile=mcp-app"],
                },
                # SEP-2663 Tasks
                "io.modelcontextprotocol/tasks": {},
            },
        )
        # Deprecated: prefer request_meta ContextVar. Kept for legacy diagnostics.
        self.client_capabilities: Dict[str, Any] = {}

        # Register available tools from obsidian_tools
        self.tools: List[MCPTool] = [
            MCPTool(
                name="ping",
                description=(
                    "Test connectivity. For vault workflows load MCP prompt vault_mcp_agent_guide "
                    "(entity graph tools, scope rules, tool selection)."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                annotations={
                    "title": "Ping",
                    "readOnlyHint": True,
                    "destructiveHint": False,
                    "idempotentHint": True,
                    "openWorldHint": False,
                },
            )
        ]

        # Add all Obsidian tools (import here to avoid circular import)
        try:
            from .tools.obsidian_tools import obsidian_tools

            self.tools.extend(obsidian_tools.get_tools())
        except Exception as e:
            print(f"Warning: Could not load Obsidian tools: {e}")

        # MCP Apps tools (prep_card, lint_queue, …)
        try:
            from .apps.registry import get_app_tools

            self.tools.extend(get_app_tools())
        except Exception as e:
            print(f"Warning: Could not load MCP App tools: {e}")

        # Resources are discovered per API-key scope set (workspace roots + pins).
        self.resources: List[MCPResource] = []
        self._resources_by_scopes: Dict[Tuple[str, ...], List[MCPResource]] = {}

        # Register available prompts
        self.prompts: List[MCPPrompt] = []
        try:
            from .prompts.obsidian_prompts import obsidian_prompts

            self.prompts.extend(obsidian_prompts.get_prompts())
        except Exception as e:
            print(f"Warning: Could not load Obsidian prompts: {e}")

        # Frozen wire snapshots so tools/list and prompts/list avoid
        # re-serializing schemas on every call (SEP-2549 friendly).
        self._tools_list_snapshot: List[Dict[str, Any]] = self._build_tools_snapshot()
        self._prompts_list_snapshot: List[Dict[str, Any]] = self._build_prompts_snapshot()

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
            elif method == MCPMessageType.SERVER_DISCOVER.value:
                return await self._handle_server_discover(params)
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
            elif method == MCPMessageType.RESOURCES_TEMPLATES_LIST.value:
                return await self._handle_resources_templates_list(params)
            elif method == MCPMessageType.PROMPTS_LIST.value:
                return await self._handle_prompts_list(params)
            elif method == MCPMessageType.PROMPTS_GET.value:
                return await self._handle_prompts_get(params)
            elif method == MCPMessageType.COMPLETION_COMPLETE.value:
                return await self._handle_completion_complete(params)
            elif method == MCPMessageType.TASKS_GET.value:
                return await self._handle_tasks_get(params)
            elif method == MCPMessageType.TASKS_UPDATE.value:
                return await self._handle_tasks_update(params)
            elif method == MCPMessageType.NOTIFICATIONS_INITIALIZED.value:
                return await self._handle_notifications_initialized(params)
            else:
                raise ValueError(f"Method not found: {method}")

        except ValueError as e:
            # Re-raise ValueError to preserve it for METHOD_NOT_FOUND handling
            raise
        except Exception as e:
            raise Exception(f"Error handling {method}: {str(e)}")

    def _capabilities_dict(self) -> Dict[str, Any]:
        caps: Dict[str, Any] = {
            "tools": self.capabilities.tools,
            "resources": self.capabilities.resources,
            "prompts": self.capabilities.prompts,
            "logging": self.capabilities.logging,
            "completions": self.capabilities.completions,
        }
        if self.capabilities.extensions:
            caps["extensions"] = self.capabilities.extensions
        return caps

    def _build_tools_snapshot(self) -> List[Dict[str, Any]]:
        tool_dicts: List[Dict[str, Any]] = []
        for tool in self.tools:
            tool_dict: Dict[str, Any] = {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.inputSchema,
            }
            if tool.annotations:
                tool_dict["annotations"] = tool.annotations
            if tool.outputSchema:
                tool_dict["outputSchema"] = tool.outputSchema
            if tool.meta:
                tool_dict["_meta"] = tool.meta
            tool_dicts.append(tool_dict)
        return tool_dicts

    def _build_prompts_snapshot(self) -> List[Dict[str, Any]]:
        prompt_list: List[Dict[str, Any]] = []
        for prompt in self.prompts:
            prompt_dict: Dict[str, Any] = {
                "name": prompt.name,
                "description": prompt.description,
            }
            if prompt.arguments:
                prompt_dict["arguments"] = prompt.arguments
            prompt_list.append(prompt_dict)
        return prompt_list

    def _negotiate_version(self, requested: Optional[str]) -> str:
        if requested in self.SUPPORTED_PROTOCOL_VERSIONS:
            return requested  # type: ignore[return-value]
        return self.protocol_version

    async def _handle_initialize(
        self, params: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Handle legacy MCP initialization handshake."""
        negotiated_version = self.protocol_version
        if params:
            requested_version = params.get("protocolVersion")
            negotiated_version = self._negotiate_version(requested_version)
            client_caps = params.get("capabilities")
            if isinstance(client_caps, dict):
                self.client_capabilities = dict(client_caps)
                meta = request_meta.get()
                if meta is not None:
                    meta.client_capabilities = dict(client_caps)

        return {
            "protocolVersion": negotiated_version,
            "capabilities": self._capabilities_dict(),
            "serverInfo": self.server_info,
            "instructions": self.instructions,
        }

    async def _handle_server_discover(
        self, params: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Stateless capability discovery (2026-07-28). No session state."""
        meta = request_meta.get()
        requested = None
        if meta and meta.protocol_version:
            requested = meta.protocol_version
        elif isinstance(params, dict):
            requested = params.get("protocolVersion")
        negotiated = self._negotiate_version(requested)
        return {
            "protocolVersion": negotiated,
            "capabilities": self._capabilities_dict(),
            "serverInfo": self.server_info,
            "instructions": self.instructions,
        }

    async def _handle_ping(self, params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Handle ping request"""
        return {
            "message": "pong",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "serverInfo": self.server_info,
        }

    @staticmethod
    def _paginate(items: List[Any], cursor: Optional[str], page_size: int) -> tuple:
        """Cursor pagination (spec 2025-06-18): cursor is an opaque offset the
        client must treat as such (it's just a stringified index here, but
        callers should not parse it), returned in nextCursor and echoed back
        on the following request. Missing/None cursor starts from the top."""
        start = 0
        if cursor is not None:
            try:
                start = int(cursor)
            except (TypeError, ValueError):
                raise ValueError(f"Invalid cursor: {cursor!r}")
            if start < 0 or start > len(items):
                raise ValueError(f"Invalid cursor: {cursor!r}")
        end = start + page_size
        page = items[start:end]
        next_cursor = str(end) if end < len(items) else None
        return page, next_cursor

    async def _handle_tools_list(
        self, params: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """List available tools"""
        cursor = (params or {}).get("cursor")
        page, next_cursor = self._paginate(
            self._tools_list_snapshot, cursor, self.TOOLS_PAGE_SIZE
        )

        result: Dict[str, Any] = {
            "tools": copy.deepcopy(page),
            "ttlMs": self.TOOLS_LIST_TTL_MS,
            "cacheScope": "private",
        }
        if next_cursor is not None:
            result["nextCursor"] = next_cursor
        return result

    async def _run_obsidian_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        from .tools.obsidian_tools import obsidian_tools

        result = await obsidian_tools.execute_tool(tool_name, arguments)
        if (
            isinstance(result, dict)
            and "metadata" in result
            and "structuredContent" not in result
        ):
            result["structuredContent"] = result["metadata"]
        return result

    async def _maybe_run_as_task(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """If client supports tasks and tool is async-eligible, start a task."""
        from .tasks import ASYNC_TOOL_NAMES, task_handle_result, task_store

        if tool_name not in ASYNC_TOOL_NAMES:
            return None
        meta = request_meta.get()
        if meta is None or not meta.supports_tasks():
            return None
        ctx = workspace_ctx.get()
        if ctx is None:
            return None

        # Capture auth context for the background worker
        identity = ctx.identity
        auth_ctx = ctx
        task_id = await task_store.create_task(identity=identity, tool_name=tool_name)

        async def _worker() -> None:
            token = workspace_ctx.set(auth_ctx)
            try:
                result = await self._run_obsidian_tool(tool_name, arguments)
                await task_store.complete_task(task_id, result=result)
            except Exception as e:
                await task_store.complete_task(task_id, error=str(e))
            finally:
                workspace_ctx.reset(token)

        asyncio.create_task(_worker())
        return task_handle_result(task_id, tool_name)

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

        # Execute the tool
        if tool_name == "ping":
            text = f"Pong! Tool called successfully at {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}"
            try:
                from .tools.obsidian_tools import obsidian_tools

                client = obsidian_tools.client
                if client is not None:
                    vault_ok = await client.health_check()
                    sync = client._sync_health()
                    text += f"\nVault path readable: {vault_ok}"
                    if sync["configured"]:
                        text += (
                            f"\nSync: {'fresh' if sync['fresh'] else 'STALE'} "
                            f"(last write {sync['age_seconds']:.0f}s ago)"
                        )
                    else:
                        text += "\nSync: obsidian-headless not configured on this host"
            except Exception:
                pass
            return {"content": [{"type": "text", "text": text}]}

        try:
            from .tools.obsidian_tools import OBSIDIAN_ROUTED_TOOL_NAMES, obsidian_tools
        except Exception:
            OBSIDIAN_ROUTED_TOOL_NAMES = frozenset()
            obsidian_tools = None  # type: ignore

        if tool_name in OBSIDIAN_ROUTED_TOOL_NAMES and obsidian_tools is not None:
            try:
                async_result = await self._maybe_run_as_task(
                    tool_name, arguments or {}
                )
                if async_result is not None:
                    return async_result
                return await self._run_obsidian_tool(tool_name, arguments or {})
            except Exception as e:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"❌ Obsidian tool '{tool_name}' failed: {str(e)}",
                        }
                    ],
                    "isError": True,
                }

        try:
            from .apps.registry import APP_TOOL_NAMES, execute_app_tool
        except Exception:
            APP_TOOL_NAMES = frozenset()
            execute_app_tool = None  # type: ignore

        if tool_name in APP_TOOL_NAMES and execute_app_tool is not None:
            try:
                result = await execute_app_tool(tool_name, arguments)
            except Exception as e:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"❌ App tool '{tool_name}' failed: {str(e)}",
                        }
                    ],
                    "isError": True,
                }
            if (
                isinstance(result, dict)
                and "metadata" in result
                and "structuredContent" not in result
            ):
                result["structuredContent"] = result["metadata"]
            return result

        return {
            "content": [
                {
                    "type": "text",
                    "text": f"❌ Unknown tool '{tool_name}'.",
                }
            ],
            "isError": True,
        }

    async def _handle_resources_list(
        self, params: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """List available resources"""
        # Load resources dynamically from vault
        await self._ensure_resources_loaded()

        cursor = (params or {}).get("cursor")
        page, next_cursor = self._paginate(self.resources, cursor, self.RESOURCES_PAGE_SIZE)

        result: Dict[str, Any] = {
            "resources": [
                {
                    "uri": resource.uri,
                    "name": resource.name,
                    "description": resource.description,
                    "mimeType": resource.mimeType,
                    **({"_meta": resource.meta} if resource.meta else {}),
                }
                for resource in page
            ],
            "ttlMs": self.RESOURCES_LIST_TTL_MS,
            "cacheScope": "private",
        }
        if next_cursor is not None:
            result["nextCursor"] = next_cursor
        return result

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

            # Add metadata / _meta if available (MCP Apps hosts read `_meta`)
            if content.metadata:
                result["contents"][0]["metadata"] = content.metadata
                result["contents"][0]["_meta"] = content.metadata

            # SEP-2549 cache hints on resources/read (UI bundles especially)
            result["ttlMs"] = self.RESOURCES_READ_TTL_MS
            result["cacheScope"] = "private"

            return result

        except PermissionError as e:
            raise ValueError(str(e))
        except Exception as e:
            # If ObsidianResources fails, provide a helpful error
            raise ValueError(f"Failed to read resource {uri}: {str(e)}")

    async def _handle_resources_templates_list(
        self, params: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """List RFC 6570 URI templates (spec 2025-06-18) a client can fill in
        itself, without needing a resources/list round trip first."""
        try:
            from .resources.obsidian_resources import get_obsidian_resources

            resources_handler = get_obsidian_resources()
            templates = resources_handler.list_resource_templates()
        except Exception as e:
            print(f"Warning: Could not load resource templates: {e}")
            templates = []

        return {
            "resourceTemplates": [
                {
                    "uriTemplate": t.uriTemplate,
                    "name": t.name,
                    **({"description": t.description} if t.description else {}),
                    **({"mimeType": t.mimeType} if t.mimeType else {}),
                }
                for t in templates
            ]
        }

    def add_tool(self, tool: MCPTool):
        """Add a new tool to the server"""
        self.tools.append(tool)

    def add_resource(self, resource: MCPResource):
        """Add a new resource to the server"""
        self.resources.append(resource)

    async def _ensure_resources_loaded(self):
        """Load resources for the current API-key scope set (cached per scopes)."""
        from .scope import get_effective_workspace_context

        scopes = tuple(get_effective_workspace_context().allowed_scopes)
        cached = self._resources_by_scopes.get(scopes)
        if cached is not None:
            self.resources = cached
            return

        try:
            from .resources.obsidian_resources import get_obsidian_resources

            resources_handler = get_obsidian_resources()
            discovered = await resources_handler.discover_resources()
            self._resources_by_scopes[scopes] = discovered
            self.resources = discovered
        except Exception as e:
            print(f"Warning: Could not load resources: {e}")
            self._resources_by_scopes[scopes] = []
            self.resources = []

    def invalidate_resources_cache(self):
        """Force reload of resources on next request"""
        self._resources_by_scopes.clear()
        self.resources = []

        # Also invalidate the ObsidianResources content cache
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
        return {
            "prompts": copy.deepcopy(self._prompts_list_snapshot),
            "ttlMs": self.PROMPTS_LIST_TTL_MS,
            "cacheScope": "private",
        }

    async def _handle_tasks_get(
        self, params: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Poll a background task (io.modelcontextprotocol/tasks)."""
        from .tasks import task_store

        if not params or not params.get("taskId"):
            raise ValueError("Missing taskId")
        ctx = workspace_ctx.get()
        if ctx is None:
            raise ValueError("Not authenticated")
        task = await task_store.get_task(str(params["taskId"]), ctx.identity)
        if task is None:
            raise ValueError(f"Unknown taskId: {params['taskId']}")
        return task

    async def _handle_tasks_update(
        self, params: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Cancel or acknowledge a task. MRTR input is a later follow-up."""
        from .tasks import STATUS_CANCELLED, task_store

        if not params or not params.get("taskId"):
            raise ValueError("Missing taskId")
        ctx = workspace_ctx.get()
        if ctx is None:
            raise ValueError("Not authenticated")
        action = (params.get("status") or params.get("action") or "").lower()
        if action in ("cancelled", "canceled", "cancel"):
            ok = await task_store.cancel_task(str(params["taskId"]), ctx.identity)
            if not ok:
                task = await task_store.get_task(str(params["taskId"]), ctx.identity)
                if task is None:
                    raise ValueError(f"Unknown taskId: {params['taskId']}")
                return task
            task = await task_store.get_task(str(params["taskId"]), ctx.identity)
            return task or {"taskId": params["taskId"], "status": STATUS_CANCELLED}
        # No-op update: return current state
        task = await task_store.get_task(str(params["taskId"]), ctx.identity)
        if task is None:
            raise ValueError(f"Unknown taskId: {params['taskId']}")
        return task

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

            description = _PROMPTS_GET_DESCRIPTIONS.get(
                name,
                f"MCP prompt: {name}",
            )
            return {
                "description": description,
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

    # Static argument-name -> candidate list for prompts whose completion
    # set doesn't depend on live vault state.
    _PROMPT_ARG_ENUMS: Dict[tuple, List[str]] = {
        ("note_template_system", "note_type"): [
            "daily", "project", "area", "seed", "resource", "knowledge",
        ],
    }

    async def _handle_completion_complete(
        self, params: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """completion/complete (spec 2025-06-18): argument-value autocomplete
        for prompts. Only ref/prompt is supported (this server has no
        resource templates with fillable variables beyond the note path,
        which isn't a meaningful completion target)."""
        params = params or {}
        ref = params.get("ref") or {}
        argument = params.get("argument") or {}
        arg_name = argument.get("name")
        arg_value = str(argument.get("value") or "")

        candidates: List[str] = []
        if ref.get("type") == "ref/prompt":
            prompt_name = ref.get("name")
            static = self._PROMPT_ARG_ENUMS.get((prompt_name, arg_name))
            if static is not None:
                candidates = static
            elif prompt_name == "meeting_prep_workflow" and arg_name == "entity_name":
                candidates = await self._complete_entity_names()

        matches = [c for c in candidates if c.lower().startswith(arg_value.lower())]
        return {
            "completion": {
                "values": matches[:100],
                "total": len(matches),
                "hasMore": len(matches) > 100,
            }
        }

    async def _complete_entity_names(self) -> List[str]:
        """Live work-entity name candidates (filename stems), best-effort:
        empty list if no vault is configured or the scan fails, rather than
        erroring out a completion request."""
        try:
            from pathlib import Path

            from .tools.obsidian_tools import obsidian_tools

            vi = obsidian_tools._get_vault_intel()
            entities = await vi._entity_notes(None)
            return sorted({Path(n.path).stem for n in entities})
        except Exception:
            return []

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


# Global MCP handler instance
mcp_handler = MCPProtocolHandler()
