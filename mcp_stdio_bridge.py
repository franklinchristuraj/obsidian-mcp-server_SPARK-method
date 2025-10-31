#!/usr/bin/env python3
"""
MCP Stdio Bridge for Claude Desktop
Bridges Claude Desktop's stdio transport to HTTP MCP server
"""
import json
import sys
import asyncio
import httpx
import signal
from typing import Dict, Any, Optional


class MCPStdioBridge:
    """
    Stdio bridge that converts MCP stdio protocol to HTTP requests
    """

    def __init__(self):
        import os
        self.server_url = os.getenv("MCP_SERVER_URL", "https://mcp.ziksaka.com/mcp")
        self.api_key = os.getenv("MCP_API_KEY")
        if not self.api_key:
            raise ValueError(
                "MCP_API_KEY environment variable is required. "
                "Set it with: export MCP_API_KEY='your-api-key'"
            )
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        self.running = True

        # Handle SIGTERM gracefully
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.running = False
        sys.stderr.write("MCP bridge shutting down...\n")
        sys.stderr.flush()

    async def forward_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Forward MCP request to HTTP server"""
        request_id = request.get("id")

        # Handle notifications (requests without id) - don't send responses
        if request_id is None and request.get("method", "").startswith(
            "notifications/"
        ):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    await client.post(
                        self.server_url, json=request, headers=self.headers
                    )
                # For notifications, don't return a response
                return None
            except Exception:
                # Ignore errors for notifications
                return None

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.server_url, json=request, headers=self.headers
                )
                response.raise_for_status()
                server_response = response.json()

                # Ensure the response has the correct structure
                if "jsonrpc" not in server_response:
                    server_response["jsonrpc"] = "2.0"
                if "id" not in server_response and request_id is not None:
                    server_response["id"] = request_id

                return server_response

        except httpx.HTTPStatusError as e:
            error_message = f"HTTP {e.response.status_code}"
            try:
                error_detail = e.response.json()
                if "detail" in error_detail:
                    error_message = error_detail["detail"]
            except:
                error_message = e.response.text[:200]

            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32603,
                    "message": error_message,
                },
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32603, "message": f"Connection error: {str(e)}"},
            }

    async def run(self):
        """Main stdio loop"""
        sys.stderr.write("MCP stdio bridge starting...\n")
        sys.stderr.flush()

        try:
            while self.running:
                try:
                    # Read line from stdin (blocking)
                    line = await asyncio.get_event_loop().run_in_executor(
                        None, sys.stdin.readline
                    )

                    if not line:  # EOF
                        break

                    line = line.strip()
                    if not line:
                        continue

                    # Parse JSON-RPC request
                    try:
                        request = json.loads(line)
                        sys.stderr.write(
                            f"Received: {request.get('method', 'unknown')}\n"
                        )
                        sys.stderr.flush()
                    except json.JSONDecodeError as e:
                        sys.stderr.write(f"JSON decode error: {e}\n")
                        sys.stderr.flush()
                        continue

                    # Forward to HTTP server
                    response = await self.forward_request(request)

                    # Only send response if we got one (notifications return None)
                    if response is not None:
                        response_line = json.dumps(response)
                        print(response_line, flush=True)

                        sys.stderr.write(
                            f"Sent response for: {request.get('method', 'unknown')}\n"
                        )
                        sys.stderr.flush()
                    else:
                        sys.stderr.write(
                            f"No response for notification: {request.get('method', 'unknown')}\n"
                        )
                        sys.stderr.flush()

                except KeyboardInterrupt:
                    break
                except Exception as e:
                    sys.stderr.write(f"Error in main loop: {e}\n")
                    sys.stderr.flush()

        except Exception as e:
            sys.stderr.write(f"Fatal error: {e}\n")
            sys.stderr.flush()
        finally:
            sys.stderr.write("MCP bridge terminated.\n")
            sys.stderr.flush()


async def main():
    """Entry point"""
    bridge = MCPStdioBridge()
    await bridge.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.stderr.write("Interrupted\n")
        sys.exit(0)
    except Exception as e:
        sys.stderr.write(f"Fatal: {e}\n")
        sys.exit(1)
