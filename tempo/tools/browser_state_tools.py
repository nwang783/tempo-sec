"""
Browser state tools.

Tools for retrieving browser state (cookies, storage, etc.).
"""

from typing import Any, TYPE_CHECKING

from tempo.tools.base import Tool, ToolCategory, ToolResult, ToolSchema

if TYPE_CHECKING:
    from tempo.infra.playwright_mcp import PlaywrightMCPClient


class GetBrowserStateTool(Tool):
    """
    Get the current browser state (cookies, local storage, session storage).
    
    Useful for persisting session state or debugging.
    """
    
    name = "get_browser_state"
    description = (
        "Get the current browser state including cookies, local storage, and session storage. "
        "Useful for persisting session state between tasks."
    )
    category = ToolCategory.BROWSING
    
    def __init__(self, client: "PlaywrightMCPClient"):
        self.client = client
        
    async def execute(self, **kwargs) -> ToolResult:
        """
        Execute the tool.
        
        Returns:
            ToolResult with browser state in metadata and full details in output.
        """
        try:
            state = await self.client.get_full_state()
            
            if "error" in state:
                return ToolResult(
                    success=False,
                    output=f"Failed to get browser state: {state['error']}",
                    error=state["error"],
                )
            
            # Format full output with actual values
            cookies = state.get("cookies", [])
            local_storage = state.get("local_storage", {})
            session_storage = state.get("session_storage", {})
            url = state.get("url", "unknown")
            
            lines = [f"## Browser State for {url}\n"]
            
            # Cookies
            lines.append(f"### Cookies ({len(cookies)})")
            if cookies:
                for cookie in cookies:
                    name = cookie.get("name", "?")
                    value = cookie.get("value", "")
                    # Truncate very long values
                    if len(value) > 100:
                        value = value[:100] + "..."
                    lines.append(f"- **{name}**: `{value}`")
            else:
                lines.append("- (none)")
            lines.append("")
            
            # Local Storage
            lines.append(f"### Local Storage ({len(local_storage)} keys)")
            if local_storage:
                for key, value in local_storage.items():
                    # Truncate very long values
                    if len(str(value)) > 100:
                        value = str(value)[:100] + "..."
                    lines.append(f"- **{key}**: `{value}`")
            else:
                lines.append("- (none)")
            lines.append("")
            
            # Session Storage
            lines.append(f"### Session Storage ({len(session_storage)} keys)")
            if session_storage:
                for key, value in session_storage.items():
                    # Truncate very long values
                    if len(str(value)) > 100:
                        value = str(value)[:100] + "..."
                    lines.append(f"- **{key}**: `{value}`")
            else:
                lines.append("- (none)")
            
            output = "\n".join(lines)
            
            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "browser_state": state
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                output=f"Error getting browser state: {e}",
                error=str(e),
            )
            
    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            },
        )
