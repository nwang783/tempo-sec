"""
Complete Browser Task Tool.

Tool for the browser agent to signal task completion and report findings.
"""

from tempo.tools.base import Tool, ToolCategory, ToolResult, ToolSchema


class CompleteBrowserTaskTool(Tool):
    """
    Signal browser task completion and report findings.
    
    This is the terminal tool for the browser agent - when called,
    the browser agent stops and returns findings to the parent agent.
    """
    
    name = "complete_browser_task"
    description = "Signal that the browser task is complete and report findings back to the caller"
    category = ToolCategory.META
    
    async def execute(
        self,
        findings: str,
        success: bool = True,
        extracted_data: str = "",
        purpose: str = "",
        **kwargs,
    ) -> ToolResult:
        """
        Complete the browser task and report findings.
        
        Args:
            findings: Summary of what was found/accomplished during browsing
            success: Whether the task was completed successfully
            extracted_data: Any specific data extracted (URLs, text, form values, etc.)
            
        Returns:
            ToolResult with completion metadata
        """
        output_parts = [f"Browser task completed: {findings}"]
        
        if extracted_data:
            output_parts.append(f"\nExtracted data:\n{extracted_data}")
        
        if not success:
            output_parts.append("\n[Task marked as unsuccessful]")
        
        return ToolResult(
            success=True,  # Tool execution succeeded even if task didn't
            output="\n".join(output_parts),
            metadata={
                "browser_task_complete": True,
                "findings": findings,
                "task_success": success,
                "extracted_data": extracted_data,
            },
        )
    
    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "findings": {
                        "type": "string",
                        "description": "Summary of what was found or accomplished during the browser task",
                    },
                    "success": {
                        "type": "boolean",
                        "description": "Whether the task was completed successfully (default: true)",
                        "default": True,
                    },
                    "extracted_data": {
                        "type": "string", 
                        "description": "Any specific data extracted during browsing (URLs, text, form data, etc.)",
                        "default": "",
                    },
                },
                "required": ["findings"],
            },
        )
