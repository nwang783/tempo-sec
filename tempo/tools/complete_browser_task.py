"""
Complete Browser Task Tool.

Tool for the browser subagent to sign off its task and report back to the parent agent.
"""

from typing import Any

from tempo.tools.base import Tool, ToolCategory, ToolResult, ToolSchema


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
                "findings": summary,
                "task_success": success,
                "extracted_data": outputs or {},
                "notes": notes,
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
                        "description": "Brief summary of what was accomplished or why the task failed",
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
