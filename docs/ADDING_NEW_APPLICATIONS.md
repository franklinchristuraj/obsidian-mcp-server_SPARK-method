# Adding New Applications to the Multi-Application MCP Server

This guide explains how to add new application integrations to the Multi-Application MCP Server. The architecture is designed to make this process straightforward and consistent.

## 🏗️ Architecture Overview

The server uses a modular, prefix-based architecture:
- **Clients** (`src/clients/`): API client modules for each application
- **Tools** (`src/tools/`): MCP tool implementations for each application  
- **Prefix-based routing**: Tools are routed based on their name prefix (e.g., `obs_`, `notion_`, `github_`)

## 📋 Step-by-Step Integration Guide

### Step 1: Create the API Client

Create a new client file in `src/clients/`:

```python
# src/clients/your_app_client.py
"""
YourApp REST API Client Wrapper
Provides access to YourApp API for [description]
"""
import httpx
import os
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

@dataclass
class YourAppDataModel:
    """Data structure for YourApp entities"""
    id: str
    name: str
    # Add other fields as needed

class YourAppAPIError(Exception):
    """Custom exception for YourApp API errors"""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code

class YourAppClient:
    """YourApp REST API client"""
    
    def __init__(self, api_token: Optional[str] = None):
        self.api_token = api_token or os.getenv("YOURAPP_API_TOKEN")
        if not self.api_token:
            raise ValueError("YourApp API token is required. Set YOURAPP_API_TOKEN environment variable.")
        
        self.base_url = "https://api.yourapp.com/v1"
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }
    
    async def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """Make HTTP request to YourApp API"""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=self.headers,
                    json=data if data else None
                )
                
                if response.status_code == 200:
                    return response.json() if response.content else {}
                elif response.status_code == 401:
                    raise YourAppAPIError("Unauthorized: Invalid API token", 401)
                elif response.status_code == 404:
                    raise YourAppAPIError("Not found: Resource does not exist", 404)
                else:
                    raise YourAppAPIError(f"HTTP {response.status_code}: {response.text}", response.status_code)
                    
        except httpx.RequestError as e:
            raise YourAppAPIError(f"Request failed: {str(e)}")
    
    # Add your API methods here
    async def get_items(self) -> List[YourAppDataModel]:
        """Get items from YourApp"""
        response = await self._make_request("GET", "items")
        return [YourAppDataModel(**item) for item in response]
    
    async def create_item(self, name: str) -> YourAppDataModel:
        """Create a new item in YourApp"""
        data = {"name": name}
        response = await self._make_request("POST", "items", data=data)
        return YourAppDataModel(**response)
```

### Step 2: Create the MCP Tools

Create a new tools file in `src/tools/`:

```python
# src/tools/your_app_tools.py
"""
YourApp MCP Tools Implementation
Tools for YourApp integration using the YourAppClient
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
from src.clients.your_app_client import YourAppClient, YourAppAPIError
from ..types import MCPTool

class YourAppTools:
    """Implementation of MCP tools for YourApp operations"""

    def __init__(self):
        self.client = None
        self._initialize_client()

    def _initialize_client(self):
        """Initialize YourAppClient with error handling"""
        try:
            self.client = YourAppClient()
        except ValueError as e:
            print(f"Warning: YourAppClient not initialized: {e}")
            self.client = None

    def get_tools(self) -> List[MCPTool]:
        """Get all available MCP tools"""
        return [
            MCPTool(
                name="yourapp_get_items",
                description="Get items from YourApp",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            ),
            MCPTool(
                name="yourapp_create_item",
                description="Create a new item in YourApp",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Item name (required)",
                        },
                    },
                    "required": ["name"],
                    "additionalProperties": False,
                },
            ),
            # Add more tools as needed
        ]

    async def get_items(self) -> Dict[str, Any]:
        """Tool: Get items from YourApp"""
        if not self.client:
            raise ValueError("YourApp client not initialized. Check YOURAPP_API_TOKEN.")

        try:
            items = await self.client.get_items()
            
            response_text = f"Found {len(items)} items:\n\n"
            for i, item in enumerate(items, 1):
                response_text += f"{i}. **{item.name}** (ID: {item.id})\n"

            return {
                "content": [{"type": "text", "text": response_text}],
                "metadata": {
                    "total_items": len(items),
                    "items": [{"id": item.id, "name": item.name} for item in items],
                },
            }

        except YourAppAPIError as e:
            raise ValueError(f"Failed to get items: {e.message}")

    async def create_item(self, name: str) -> Dict[str, Any]:
        """Tool: Create a new item"""
        if not self.client:
            raise ValueError("YourApp client not initialized. Check YOURAPP_API_TOKEN.")

        try:
            item = await self.client.create_item(name)
            
            return {
                "content": [{"type": "text", "text": f"✅ Successfully created item: **{item.name}** (ID: {item.id})"}],
                "metadata": {
                    "item_id": item.id,
                    "name": item.name,
                    "created_at": datetime.now().isoformat(),
                },
            }

        except YourAppAPIError as e:
            raise ValueError(f"Failed to create item: {e.message}")

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool by name with given arguments"""
        tool_methods = {
            "yourapp_get_items": self.get_items,
            "yourapp_create_item": self.create_item,
        }

        if tool_name not in tool_methods:
            raise ValueError(f"Unknown tool: {tool_name}")

        method = tool_methods[tool_name]
        try:
            return await method(**arguments)
        except TypeError as e:
            raise ValueError(f"Invalid arguments for tool '{tool_name}': {str(e)}")

# Global instance
your_app_tools = YourAppTools()
```

### Step 3: Update the MCP Server

Add your application to the MCP server in `src/mcp_server.py`:

```python
# In the __init__ method, add after the Obsidian tools loading:
# Add YourApp tools
try:
    from .tools.your_app_tools import your_app_tools
    self.tools.extend(your_app_tools.get_tools())
except Exception as e:
    print(f"Warning: Could not load YourApp tools: {e}")
```

```python
# In the _handle_tools_call method, add after the Obsidian routing:
elif tool_name.startswith("yourapp_"):
    # Execute YourApp tools
    try:
        from .tools.your_app_tools import your_app_tools
        return await your_app_tools.execute_tool(tool_name, arguments)
    except Exception as e:
        return {
            "content": [
                {"type": "text", "text": f"❌ YourApp tool '{tool_name}' failed: {str(e)}"}
            ]
        }
```

### Step 4: Update Documentation

Update the README.md to include your new application:

```markdown
#### 🔧 YourApp Tools (yourapp_ prefix)
1. **yourapp_get_items** - Get items from YourApp
2. **yourapp_create_item** - Create new items
```

## 🎯 Best Practices

### Naming Conventions
- **Client file**: `your_app_client.py` (snake_case)
- **Tools file**: `your_app_tools.py` (snake_case)
- **Tool prefix**: `yourapp_` (lowercase, no spaces)
- **Class names**: `YourAppClient`, `YourAppTools` (PascalCase)

### Error Handling
- Create custom exception classes for API errors
- Provide meaningful error messages
- Handle authentication failures gracefully
- Include status codes when available

### Data Models
- Use `@dataclass` for structured data
- Include type hints for all fields
- Provide sensible defaults where appropriate
- Document field purposes in docstrings

### Tool Implementation
- Keep tools focused on single operations
- Provide clear descriptions and examples
- Include comprehensive input validation
- Return structured metadata for programmatic use

### Testing
- Test client initialization with missing credentials
- Test tool execution with mock responses
- Verify error handling for API failures
- Include integration tests if possible

## 🔧 Environment Variables

Add your application's environment variables to the documentation:

```bash
# YourApp Integration
YOURAPP_API_TOKEN=your_api_token_here
```

## 📝 Example Applications to Consider

Here are some popular applications that would be good candidates for integration:

- **Notion** (`notion_*`): Note-taking and database management
- **GitHub** (`github_*`): Repository and issue management  
- **Google Calendar** (`gcal_*`): Calendar and event management
- **Slack** (`slack_*`): Team communication and channel management
- **Trello** (`trello_*`): Board and card management
- **Linear** (`linear_*`): Issue tracking and project management
- **Airtable** (`airtable_*`): Database and record management

## 🚀 Testing Your Integration

1. **Create a test script** following the pattern in `test_multi_app.py`
2. **Test without credentials** to ensure graceful degradation
3. **Test with valid credentials** to verify functionality
4. **Test error conditions** to ensure proper error handling
5. **Verify tool discovery** in the tools list

## 💡 Tips for Success

- **Start small**: Implement 2-3 core tools first, then expand
- **Follow existing patterns**: Use the Obsidian integration as a reference
- **Test thoroughly**: Both happy path and error conditions
- **Document well**: Clear descriptions help users understand capabilities
- **Handle rate limits**: Many APIs have usage restrictions
- **Consider caching**: For frequently accessed data
- **Plan for pagination**: Large datasets may need chunked responses

The architecture is designed to make adding new applications straightforward while maintaining consistency and reliability across all integrations.
