"""
Tool for viewing specific ranges of previous tool outputs.

This tool allows the agent to request specific character ranges from
large tool outputs, enabling efficient navigation of large results
without overwhelming the context window.
"""

from tempo.tools.base import Tool, ToolResult, ToolSchema, ToolCategory
from tempo.infra.protocols import ToolOutputViewer


class ViewToolOutputTool(Tool):
    """View a specific range of a previous tool's output."""
    
    name = "view_tool_output"
    description = "View a specific character range of a previous tool's output. Use this when a tool output was truncated and you need to see more."
    category = ToolCategory.META
    
    def __init__(self, context_store: ToolOutputViewer):
        """
        Initialize the tool.
        
        Args:
            context_store: Any component implementing ToolOutputViewer protocol
        """
        self.context_store = context_store

    
    async def execute(
        self,
        tool_call_id: str,
        start_char: int = 0,
        end_char: int = 10000,
        purpose: str = "",
    ) -> ToolResult:
        """
        View a specific character range of a previous tool's output.
        
        Args:
            tool_call_id: ID of the tool call to view
            start_char: Starting character position (0-indexed)
            end_char: Ending character position (exclusive)
            purpose: Why you are viewing this range
            
        Returns:
            ToolResult with the requested character range
        """
        # Search for the tool call in context
        tool_call = self._find_tool_call(tool_call_id)
        
        if tool_call is None:
            return ToolResult(
                success=False,
                output="",
                error=f"Tool call not found: {tool_call_id}",
            )
        
        # Get the RAW output (not summary - the purpose is to view original large output)
        output = tool_call.raw_output or ""
        total = len(output)
        
        # Validate range
        start_char = max(0, start_char)
        end_char = min(total, end_char)
        
        if start_char >= end_char:
            return ToolResult(
                success=False,
                output="",
                error=f"Invalid range: start_char ({start_char}) >= end_char ({end_char})",
            )
        
        # Extract the range
        content = output[start_char:end_char]
        
        return ToolResult(
            success=True,
            output=f"[Showing chars {start_char}-{end_char} of {total} total]\n{content}",
            metadata={
                "tool_call_id": tool_call_id,
                "start_char": start_char,
                "end_char": end_char,
                "total_chars": total,
            },
        )
    
    def _find_tool_call(self, tool_call_id: str):
        """Find a tool call by ID in the context store."""
        from tempo.context.frame import ToolCall
        
        # Search through all frames
        frame_id = self.context_store._current_frame_id
        while frame_id is not None:
            frame = self.context_store._frames.get(frame_id)
            if frame is None:
                break
            for tc in frame.tool_calls:
                if tc.id == tool_call_id:
                    return tc
            frame_id = frame.parent_id
        return None
    
    def get_schema(self) -> ToolSchema:
        """Return the JSON schema for this tool's parameters."""
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "tool_call_id": {
                        "type": "string",
                        "description": "The ID of the tool call whose output you want to view",
                    },
                    "start_char": {
                        "type": "integer",
                        "description": "Starting character position (0-indexed). Default: 0",
                        "default": 0,
                    },
                    "end_char": {
                        "type": "integer",
                        "description": "Ending character position (exclusive). Default: 10000",
                        "default": 10000,
                    },
                    "purpose": {
                        "type": "string",
                        "description": "Why you are viewing this range",
                    },
                },
                "required": ["tool_call_id", "purpose"],
            },
        )
