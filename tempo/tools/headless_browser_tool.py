"""
Headless Browser Tool.

Non-visual browser automation via Playwright MCP for faster, lightweight browsing.
"""

import logging
from typing import TYPE_CHECKING, Any

from tempo.tools.base import Tool, ToolCategory, ToolResult, ToolSchema

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from tempo.infra.container import ContainerManager
    from tempo.infra.protocols import FindingsUpdater


# Map of supported actions to their Playwright MCP tool names
ACTION_TO_MCP_TOOL = {
    # Navigation
    "navigate": "browser_navigate",
    "go_back": "browser_navigate_back", 
    "close": "browser_close",
    
    # Interaction
    "click": "browser_click",
    "select_option": "browser_select_option",
    "hover": "browser_hover",
    "drag": "browser_drag",
    
    # State
    "snapshot": "browser_snapshot",
    "screenshot": "browser_take_screenshot",
    
    # JavaScript
    "evaluate_js": "browser_run_code",
    
    # Introspection
    "get_network_requests": "browser_network_requests",
    
    # Advanced
    "handle_dialog": "browser_handle_dialog",
}


class HeadlessBrowserTool(Tool):
    """
    Non-visual browser automation via Playwright MCP.
    
    This tool provides faster, more cost-effective browser automation
    compared to the visual_browser_task tool. It wraps the Playwright MCP
    server for headless browser control using stdio transport.
    
    Best for:
    - Authenticated testing (login flows, session-based API discovery)
    - API discovery via network capture
    - JavaScript execution in authenticated contexts
    - Session reuse across multiple test steps
    
    Features:
    - Stdio transport for reliable request/response handling
    - Session ID tracking for authenticated workflows
    - Full Playwright MCP toolset access
    """
    
    name = "headless_browser"
    description = (
        "Execute browser actions without visual rendering. "
        "Faster and more cost-effective than visual_browser_task. "
        "Use for: login flows, authenticated API testing, network request capture. "
        "Returns a session_id that can be reused for continued authenticated access."
    )
    category = ToolCategory.BROWSING
    
    def __init__(
        self,
        container_manager: "ContainerManager | None" = None,
        findings_updater: "FindingsUpdater | None" = None,
        headless: bool = True,
        browser: str = "chromium",
        timeout: int = 60000,
    ):
        """
        Initialize the headless browser tool.
        
        Args:
            container_manager: Container for sandboxed execution (optional)
            findings_updater: Findings document for context (optional)
            headless: Whether to run browser in headless mode
            browser: Browser engine (chromium, firefox, webkit)
            timeout: Default action timeout in milliseconds
        """
        self._container_manager = container_manager
        self._findings_updater = findings_updater
        self._headless = headless
        self._browser = browser
        self._timeout = timeout
        self._client: Any = None  # Lazy-initialized PlaywrightMCPClient
        
    async def _ensure_client(self) -> Any:
        """Ensure the MCP client is initialized and server is running."""
        if self._client is None:
            from tempo.infra.playwright_mcp import PlaywrightMCPClient
            
            self._client = PlaywrightMCPClient(
                headless=self._headless,
                browser=self._browser,
                timeout=self._timeout,
            )
            await self._client.start_server()
            
        return self._client
    
    async def execute(
        self,
        action: str,
        params: dict[str, Any] | None = None,
        session_id: str = "",
        purpose: str = "",
        **kwargs,
    ) -> ToolResult:
        """
        Execute a browser action via Playwright MCP.
        
        Args:
            action: The browser action to perform (navigate, click, type, etc.)
            params: Action-specific parameters
            session_id: Optional session ID to reuse existing browser state
            purpose: Why this action is being performed
            **kwargs: Additional arguments (ignored)
            
        Returns:
            ToolResult with action output and session_id for subsequent calls
        """
        # Validate action
        if action not in ACTION_TO_MCP_TOOL:
            available = ", ".join(sorted(ACTION_TO_MCP_TOOL.keys()))
            return ToolResult(
                success=False,
                output="",
                error=f"Unknown action: {action}. Available actions: {available}",
            )
        
        # Get the corresponding MCP tool name
        mcp_tool = ACTION_TO_MCP_TOOL[action]
        
        # Prepare parameters
        tool_params = params or {}
        
        # Normalize element references: agents may pass {"ref": "e43"} or {"element": {"ref": "e43"}}
        # but Playwright MCP expects just the string "e43"
        if "element" in tool_params:
            element_val = tool_params["element"]
            if isinstance(element_val, dict):
                # Extract ref from object like {"ref": "e43"}
                tool_params["element"] = element_val.get("ref", str(element_val))
        elif "ref" in tool_params:
            # If ref is passed directly, use it as element
            tool_params["element"] = tool_params.pop("ref")
        
        # Special handling for common action shortcuts
        if action == "navigate" and "url" in kwargs:
            tool_params["url"] = kwargs["url"]
        if action == "type" and "text" in kwargs:
            tool_params["text"] = kwargs["text"]
        if action == "click" and "element" in kwargs:
            element_val = kwargs["element"]
            if isinstance(element_val, dict):
                tool_params["element"] = element_val.get("ref", str(element_val))
            else:
                tool_params["element"] = element_val
        if action == "evaluate_js" and "script" in kwargs:
            tool_params["script"] = kwargs["script"]

        # Map parameters to MCP expectations
        if mcp_tool in ["browser_click", "browser_hover", "browser_select_option"]:
            # These tools require 'ref', not 'element'
            if "element" in tool_params:
                tool_params["ref"] = tool_params.pop("element")
        
        elif mcp_tool == "browser_run_code":
            # Map 'script' to 'code' and wrap in async function
            if "script" in tool_params:
                script = tool_params.pop("script")
                # Wrap script in async function that receives page and uses evaluate for browser context
                tool_params["code"] = f"async (page) => {{ return await page.evaluate(async () => {{ {script} }}) }}"
            
        try:
            # Ensure client is ready
            client = await self._ensure_client()
            
            # Call the MCP tool
            result = await client.call_tool(mcp_tool, tool_params)
            
            if result.get("success"):
                return ToolResult(
                    success=True,
                    output=result.get("output", ""),
                    metadata={
                        "session_id": client.session_id,
                        "action": action,
                        "mcp_tool": mcp_tool,
                    },
                    structured_data=result.get("raw_result"),
                )
            else:
                return ToolResult(
                    success=False,
                    output=result.get("output", ""),
                    error=result.get("error", "Unknown error"),
                    metadata={
                        "session_id": client.session_id,
                        "action": action,
                        "mcp_tool": mcp_tool,
                    },
                )
                
        except Exception as e:
            logger.exception(f"Headless browser action failed: {action}")
            return ToolResult(
                success=False,
                output="",
                error=f"Headless browser error: {str(e)}",
                metadata={
                    "action": action,
                    "session_id": self._client.session_id if self._client else None,
                },
            )
    
    async def cleanup(self) -> None:
        """Stop the MCP server and cleanup resources."""
        if self._client:
            await self._client.stop_server()
            self._client = None
    
    def get_schema(self) -> ToolSchema:
        """Return the JSON schema for this tool's parameters."""
        # Build action enum description
        action_docs = []
        for action, mcp_tool in sorted(ACTION_TO_MCP_TOOL.items()):
            action_docs.append(f"  - {action}: Maps to {mcp_tool}")
        action_list = "\n".join(action_docs)
        
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": (
                            f"The browser action to perform. Available actions:\n{action_list}"
                        ),
                        "enum": list(ACTION_TO_MCP_TOOL.keys()),
                    },
                    "params": {
                        "type": "object",
                        "description": (
                            "Action-specific parameters. Common parameters:\n"
                            "  - navigate: {url: string}\n"
                            "  - click: {element: string} (element ref from snapshot)\n"
                            "  - evaluate_js: {script: string}\n"
                            "  - screenshot: {raw?: boolean}\n"
                            "  - resize: {width: number, height: number}"
                        ),
                        "additionalProperties": True,
                    },
                    "session_id": {
                        "type": "string",
                        "description": (
                            "Optional session ID from a previous call. "
                            "Pass this to reuse the same browser session for authenticated workflows."
                        ),
                        "default": "",
                    },
                },
                "required": ["action"],
            },
        )
    
    def default_summarizer(self, result: ToolResult) -> str:
        """Summarize headless browser results."""
        if not result.success:
            return f"Error: {result.error}"
            
        action = result.metadata.get("action", "unknown")
        session_id = result.metadata.get("session_id", "")
        
        summary = f"Headless browser action '{action}' completed."
        if session_id:
            summary += f" Session: {session_id}"
            
        # Truncate long outputs
        if len(result.output) > 500:
            summary += f"\nOutput: {result.output[:250]}...[truncated]...{result.output[-250:]}"
        elif result.output:
            summary += f"\nOutput: {result.output}"
            
        return summary
