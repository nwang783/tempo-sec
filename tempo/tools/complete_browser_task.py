"""
Complete Browser Task Tool.

Tool for the browser subagent to sign off its task and report back to the parent agent.
"""

from typing import Any, TYPE_CHECKING

from tempo.tools.base import Tool, ToolCategory, ToolResult, ToolSchema

if TYPE_CHECKING:
    from tempo.infra.playwright_mcp import PlaywrightMCPClient


class CompleteBrowserTaskTool(Tool):
    """
    Signal browser task completion and report results.
    
    This is the terminal tool for the BrowserSubagent.
    """
    
    name = "complete_browser_task"
    description = (
        "Signal that the browser task is complete and report findings. "
        "Use this when you have achieved the goal or cannot proceed further."
    )
    category = ToolCategory.META
    
    def __init__(self, client: "PlaywrightMCPClient | None" = None):
        """
        Initialize the tool.
        
        Args:
            client: Optional PlaywrightMCPClient to capture state from.
        """
        self.client = client
    
    async def execute(
        self,
        summary: str,
        success: bool = True,
        outputs: dict[str, Any] | None = None,
        notes: str = "",
        purpose: str = "",
    ) -> ToolResult:
        """
        Complete the browser task.
        
        Args:
            summary: Brief summary of what was accomplished
            success: Whether the task was successful
            outputs: Key-value pairs of extracted data (e.g., {"url": "...", "token": "..."})
            notes: Additional observations or details
            purpose: Why this tool is being called
            
        Returns:
            ToolResult with completion metadata
        """
        output_parts = [f"Browser task {'completed' if success else 'failed'}: {summary}"]
        
        browser_state = None
        if self.client:
            try:
                # Attempt to capture state with a short timeout
                # Note: get_full_state creates a new asyncio timestamp, so it's fast
                # providing the underlying browser_evaluate calls don't hang.
                # Since we are completing, spending an extra second to capture state is worth it.
                browser_state = await self.client.get_full_state()
                if "error" not in browser_state:
                    output_parts.append("\n[Browser state (cookies/storage) captured in metadata]")
            except Exception as e:
                # Don't fail the task if state capture fails
                output_parts.append(f"\n[Warning: Failed to capture browser state: {e}]")
        
        if outputs:
            import json
            output_parts.append(f"\nOutputs: {json.dumps(outputs, indent=2)}")
            
        if notes:
            output_parts.append(f"\nNotes: {notes}")
            
        return ToolResult(
            success=True,  # The *tool call* is successful even if the task failed
            output="\n".join(output_parts),
            metadata={
                "browser_task_complete": True,
                "task_complete": True,
                "findings": summary,
                "summary": summary,
                "task_success": success,
                "extracted_data": outputs or {},
                "notes": notes,
                "browser_state": browser_state,
            },
        )
    
    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Detailed summary of what was accomplished, including specific actions taken, pages visited, and any findings or issues encountered. Do NOT be brief.",
                    },
                    "success": {
                        "type": "boolean",
                        "description": "Whether the task was successfully completed",
                        "default": True,
                    },
                    "outputs": {
                        "type": "object",
                        "description": "Extracted data or artifacts (key-value pairs)",
                        "default": {},
                    },
                    "notes": {
                        "type": "string",
                        "description": "Additional notes, observations, or error details",
                        "default": "",
                    },
                },
                "required": ["summary"],
            },
        )
