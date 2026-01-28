"""
Playwright MCP Client.

Client for managing Playwright MCP server communication via stdio transport.
Uses JSON-RPC over stdin/stdout for reliable communication.
"""

import asyncio
import json
import logging
import os
import subprocess
import uuid
from typing import Any

logger = logging.getLogger(__name__)


class PlaywrightMCPClient:
    """
    Client for Playwright MCP server via stdio transport.
    
    This client manages communication with the Playwright MCP server
    using JSON-RPC over stdin/stdout pipes, which is more reliable than
    HTTP/SSE for long-running browser operations.
    
    Features:
    - Stdio transport for reliable request/response handling
    - Session ID tracking for authenticated workflows
    - Automatic server lifecycle management
    
    Usage:
        client = PlaywrightMCPClient()
        await client.start_server()
        result = await client.call_tool("browser_navigate", {"url": "https://example.com"})
        await client.stop_server()
    """
    
    def __init__(
        self,
        headless: bool = True,
        browser: str = "chromium",
        timeout: int = 60000,
        version: str | None = None,
        read_limit: int | None = None,
        user_data_dir: str | None = None,
    ):
        """
        Initialize the Playwright MCP client.
        
        Args:
            headless: Whether to run browser in headless mode
            browser: Browser engine to use (chromium, firefox, webkit)
            timeout: Default action timeout in milliseconds
            version: Playwright MCP npm package version (default: env TEMPO_PLAYWRIGHT_MCP_VERSION or "latest")
            read_limit: Max bytes per JSON-RPC message line (default: env TEMPO_PLAYWRIGHT_MCP_READ_LIMIT or 10MB)
            user_data_dir: Path to persistent browser profile directory. If None, uses --isolated (in-memory).
        """
        self.headless = headless
        self.browser = browser
        self.timeout = timeout
        self.version = version or os.getenv("TEMPO_PLAYWRIGHT_MCP_VERSION", "latest")
        self.read_limit = read_limit or int(os.getenv("TEMPO_PLAYWRIGHT_MCP_READ_LIMIT", str(10 * 1024 * 1024)))
        self.user_data_dir = user_data_dir
        self._process: subprocess.Popen | None = None
        self._session_id: str = str(uuid.uuid4())[:8]
        self._server_ready = False
        self._request_id = 0
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._read_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()
        
    @property
    def session_id(self) -> str:
        """Get session ID for browser state tracking."""
        return self._session_id
    
    async def start_server(self) -> None:
        """
        Start MCP server with stdio transport.
        
        Spawns: npx @playwright/mcp@<version> --headless --browser <browser>
        
        Raises:
            RuntimeError: If server fails to start
        """
        if self._server_ready:
            logger.debug("Playwright MCP server already running")
            return
            
        # Build command arguments (no --port for stdio transport)
        cmd = [
            "npx",
            f"@playwright/mcp@{self.version}",
            "--browser", self.browser,
        ]
        
        # Use persistent user-data-dir if provided, otherwise isolated mode
        if self.user_data_dir:
            cmd.extend(["--user-data-dir", self.user_data_dir])
        else:
            cmd.append("--isolated")  # In-memory profile (no persistence)
        
        if self.headless:
            cmd.append("--headless")
            
        logger.info(f"Starting Playwright MCP server (stdio): {' '.join(cmd)}")
        
        try:
            # Start server process with pipes for stdio
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=self.read_limit,
            )
            
            # Set up stream reader/writer
            self._reader = self._process.stdout
            self._writer = self._process.stdin
            
            # Give the server a moment to initialize
            await asyncio.sleep(1.0)
            
            # Check if process is still running
            if self._process.returncode is not None:
                stderr = await self._process.stderr.read()
                raise RuntimeError(f"MCP server exited immediately: {stderr.decode()}")
            
            # Send MCP initialization handshake
            await self._initialize_mcp()
            
            self._server_ready = True
            logger.info("Playwright MCP server started (stdio)")
            
        except Exception as e:
            await self.stop_server()
            raise RuntimeError(f"Failed to start Playwright MCP server: {e}") from e
    
    async def _initialize_mcp(self) -> None:
        """Send MCP initialization request to establish protocol session."""
        init_payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "tempo-headless-browser",
                    "version": "1.0.0",
                },
            },
        }
        
        result = await self._send_request(init_payload)
        if result.get("error"):
            logger.warning(f"MCP init warning: {result['error']}")
        else:
            logger.debug(f"MCP initialized: {result.get('result', {})}")
                
        # Send initialized notification (no response expected)
        notif_payload = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        }
        await self._send_notification(notif_payload)
    
    def _next_id(self) -> str:
        """Generate next request ID."""
        self._request_id += 1
        return str(self._request_id)
    
    async def _send_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Send a JSON-RPC request and wait for response.
        
        Args:
            payload: JSON-RPC request payload
            
        Returns:
            Parsed JSON-RPC response
        """
        if not self._writer or not self._reader:
            raise RuntimeError("MCP server not started")
        
        request_id = payload.get("id")
        
        # Write request atomically
        async with self._write_lock:
            message = json.dumps(payload) + "\n"
            self._writer.write(message.encode())
            await self._writer.drain()
            logger.debug(f"MCP sent: {payload.get('method', 'unknown')}")
        
        # Read response (with timeout)
        try:
            async with asyncio.timeout(self.timeout / 1000):
                async with self._read_lock:
                    while True:
                        line = await self._reader.readline()
                        if not line:
                            raise RuntimeError("MCP server closed connection")
                        
                        line = line.decode().strip()
                        if not line:
                            continue
                            
                        try:
                            response = json.loads(line)
                            # Match response to request by ID
                            if response.get("id") == request_id:
                                logger.debug(f"MCP recv: id={request_id}, has_result={bool(response.get('result'))}")
                                return response
                            # If it's a notification or different ID, log and continue
                            logger.debug(f"MCP recv (skipped): {line[:100]}")
                        except json.JSONDecodeError:
                            logger.warning(f"MCP invalid JSON: {line[:100]}")
                            
        except asyncio.TimeoutError:
            raise RuntimeError(f"MCP request timed out after {self.timeout}ms")
    
    async def _send_notification(self, payload: dict[str, Any]) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        if not self._writer:
            raise RuntimeError("MCP server not started")
        
        async with self._write_lock:
            message = json.dumps(payload) + "\n"
            self._writer.write(message.encode())
            await self._writer.drain()
            logger.debug(f"MCP notification sent: {payload.get('method', 'unknown')}")
    
    async def call_tool(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """
        Call a Playwright MCP tool.
        
        Args:
            tool_name: Name of the Playwright MCP tool to call
            params: Tool-specific parameters
            
        Returns:
            Tool result dictionary with output and any metadata
            
        Raises:
            RuntimeError: If server is not running or request fails
        """
        if not self._server_ready:
            raise RuntimeError("Playwright MCP server not started. Call start_server() first.")
            
        # Build MCP request payload
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": params,
            },
        }
        
        try:
            result = await self._send_request(payload)
            
            # Check for JSON-RPC error
            if "error" in result:
                error = result["error"]
                error_msg = error.get("message", str(error)) if isinstance(error, dict) else str(error)
                return {
                    "success": False,
                    "error": error_msg,
                    "output": "",
                }
                
            # Extract result content
            content = result.get("result", {})
            
            # Handle different content types in MCP response
            if isinstance(content, dict) and "content" in content:
                # Standard MCP content response
                items = content.get("content", [])
                output_parts = []
                for item in items:
                    if item.get("type") == "text":
                        output_parts.append(item.get("text", ""))
                output = "\n".join(output_parts)
            else:
                output = str(content)
                
            return {
                "success": True,
                "output": output,
                "raw_result": content,
            }
                
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": f"Tool call timed out after {self.timeout}ms",
                "output": "",
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Unexpected error: {e}",
                "output": "",
            }
    
    async def stop_server(self) -> None:
        """Stop MCP server and cleanup resources."""
        self._server_ready = False
        
        # Close writer
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception as e:
                logger.debug(f"Error closing writer: {e}")
            self._writer = None
            
        self._reader = None
            
        # Terminate server process
        if self._process:
            try:
                self._process.terminate()
                # Give it a moment to terminate gracefully
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    self._process.kill()
                    await asyncio.wait_for(self._process.wait(), timeout=2)
            except Exception as e:
                logger.debug(f"Error terminating MCP server: {e}")
            self._process = None
            
        logger.info("Playwright MCP server stopped")
    
    async def __aenter__(self) -> "PlaywrightMCPClient":
        """Async context manager entry - start server."""
        await self.start_server()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit - stop server."""
        await self.stop_server()

    def _extract_json_from_output(self, output: str) -> str | None:
        """Extract JSON from browser_evaluate markdown output.
        
        The MCP browser_evaluate tool returns markdown like:
        ### Result
        "[{\"name\": \"cookie\", \"value\": \"test\"}]"
        ### Ran Playwright code
        ...
        
        We need to extract just the JSON portion between ### Result and ### Ran.
        """
        if not output:
            return None
        
        # Look for ### Result section
        lines = output.split("\n")
        result_value = None
        
        for i, line in enumerate(lines):
            if line.strip() == "### Result":
                # Next non-empty line should have the value
                for j in range(i + 1, len(lines)):
                    next_line = lines[j].strip()
                    if next_line and not next_line.startswith("###"):
                        result_value = next_line
                        break
                break
        
        if result_value:
            # Remove surrounding quotes if present (JSON string is double-quoted)
            if result_value.startswith('"') and result_value.endswith('"'):
                try:
                    # The value itself is a JSON-encoded string, decode it
                    return json.loads(result_value)
                except json.JSONDecodeError:
                    return result_value.strip('"')
            return result_value
        
        return None

    async def get_cookies(self) -> list[dict[str, Any]]:
        """Get cookies from the current page context."""
        # Use document.cookie to get accessible cookies (non-HttpOnly)
        script = """() => {
            const cookies = document.cookie.split(';').map(c => {
                const [name, ...v] = c.trim().split('=');
                return { name, value: v.join('=') };
            }).filter(c => c.name);
            return JSON.stringify(cookies);
        }"""
        
        result = await self.call_tool("browser_evaluate", {"function": script})
        if result["success"] and result["output"]:
            json_str = self._extract_json_from_output(result["output"])
            if json_str:
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    logger.debug(f"Failed to parse cookies JSON: {json_str}")
        return []

    async def get_local_storage(self) -> dict[str, str]:
        """Get local storage data."""
        script = "() => JSON.stringify({...localStorage})"
        result = await self.call_tool("browser_evaluate", {"function": script})
        if result["success"] and result["output"]:
            json_str = self._extract_json_from_output(result["output"])
            if json_str:
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    logger.debug(f"Failed to parse localStorage JSON: {json_str}")
        return {}

    async def get_session_storage(self) -> dict[str, str]:
        """Get session storage data."""
        script = "() => JSON.stringify({...sessionStorage})"
        result = await self.call_tool("browser_evaluate", {"function": script})
        if result["success"] and result["output"]:
            json_str = self._extract_json_from_output(result["output"])
            if json_str:
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    logger.debug(f"Failed to parse sessionStorage JSON: {json_str}")
        return {}
        
    async def get_url(self) -> str:
        """Get current URL."""
        script = "() => window.location.href"
        result = await self.call_tool("browser_evaluate", {"function": script})
        if result["success"] and result["output"]:
            url = self._extract_json_from_output(result["output"])
            if url:
                return url.strip()
        return ""

    async def get_full_state(self) -> dict[str, Any]:
        """
        Get full browser state (cookies, storage, url).
        
        Returns:
            Dictionary containing state capture.
        """
        if not self._server_ready:
            return {}
            
        try:
            # Gather state in parallel or sequence
            # Browser ops usually serialized, so sequence is fine
            url = await self.get_url()
            cookies = await self.get_cookies()
            local_storage = await self.get_local_storage()
            session_storage = await self.get_session_storage()
            
            return {
                "url": url,
                "cookies": cookies,
                "local_storage": local_storage,
                "session_storage": session_storage,
                "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            }
        except Exception as e:
            logger.error(f"Failed to capture browser state: {e}")
            return {"error": str(e)}


# Available Playwright MCP tools
PLAYWRIGHT_MCP_TOOLS = {
    # Navigation
    "browser_navigate": {
        "description": "Navigate to a URL in the browser",
        "parameters": {
            "url": {"type": "string", "description": "URL to navigate to", "required": True},
        },
    },
    "browser_navigate_back": {
        "description": "Go back to the previous page",
        "parameters": {},
    },
    "browser_close": {
        "description": "Close the browser",
        "parameters": {},
    },
    
    # Interaction
    "browser_click": {
        "description": "Click on an element",
        "parameters": {
            "ref": {"type": "string", "description": "Element reference from snapshot (e.g., 'e59')", "required": True},
        },
    },
    "browser_type": {
        "description": "Type text into an element",
        "parameters": {
            "ref": {"type": "string", "description": "Element reference from snapshot", "required": True},
            "text": {"type": "string", "description": "Text to type", "required": True},
            "submit": {"type": "boolean", "description": "Press Enter after typing", "required": False},
        },
    },
    "browser_fill_form": {
        "description": "Fill form fields with values",
        "parameters": {
            "values": {"type": "object", "description": "Field name to value mapping", "required": True},
        },
    },
    "browser_select_option": {
        "description": "Select an option from a dropdown",
        "parameters": {
            "ref": {"type": "string", "description": "Select element reference", "required": True},
            "value": {"type": "string", "description": "Option value to select", "required": True},
        },
    },
    "browser_hover": {
        "description": "Hover over an element",
        "parameters": {
            "ref": {"type": "string", "description": "Element reference", "required": True},
        },
    },
    "browser_drag": {
        "description": "Drag from one element to another",
        "parameters": {
            "source": {"type": "string", "description": "Source element reference", "required": True},
            "target": {"type": "string", "description": "Target element reference", "required": True},
        },
    },
    "browser_press_key": {
        "description": "Press a keyboard key",
        "parameters": {
            "key": {"type": "string", "description": "Key to press (e.g., 'Enter', 'Tab', 'Escape')", "required": True},
        },
    },
    
    # State
    "browser_snapshot": {
        "description": "Get accessibility snapshot of the current page",
        "parameters": {},
    },
    "browser_take_screenshot": {
        "description": "Take a screenshot of the current page",
        "parameters": {
            "raw": {"type": "boolean", "description": "Return raw screenshot without annotations", "required": False},
        },
    },
    "browser_resize": {
        "description": "Resize the browser viewport",
        "parameters": {
            "width": {"type": "integer", "description": "Viewport width", "required": True},
            "height": {"type": "integer", "description": "Viewport height", "required": True},
        },
    },
    
    # JavaScript
    "browser_evaluate": {
        "description": "Execute JavaScript in the page context",
        "parameters": {
            "function": {"type": "string", "description": "JavaScript function to execute", "required": True},
        },
    },
    
    # Introspection
    "browser_network_requests": {
        "description": "Get captured network requests",
        "parameters": {},
    },
    "browser_console_messages": {
        "description": "Get browser console messages",
        "parameters": {},
    },
    
    # Advanced
    "browser_file_upload": {
        "description": "Upload a file to a file input element",
        "parameters": {
            "ref": {"type": "string", "description": "File input element reference", "required": True},
            "paths": {"type": "array", "description": "File paths to upload", "required": True, "items": {"type": "string"}},
        },
    },
    "browser_handle_dialog": {
        "description": "Handle a browser dialog (accept/dismiss)",
        "parameters": {
            "action": {"type": "string", "description": "Action: 'accept' or 'dismiss'", "required": True},
            "prompt_text": {"type": "string", "description": "Text to enter for prompt dialogs", "required": False},
        },
    },
}
