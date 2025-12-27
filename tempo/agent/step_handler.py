"""
Step handler for executing and processing agent steps.

Extracts tool call execution and special tool handling from the Agent class
to improve cohesion and testability.
"""

from dataclasses import dataclass
from typing import Any, Callable, TYPE_CHECKING

from tempo.context.frame import ToolCall
from tempo.tools.registry import ToolRegistry
from tempo.tools.base import ToolResult

if TYPE_CHECKING:
    from tempo.prompts.phases import Phase


@dataclass
class SpecialToolResult:
    """Result from processing a special meta tool."""
    tool_name: str
    should_continue: bool = True
    phase_transition: "Phase | None" = None
    findings: dict[str, Any] | None = None
    branch_id: str | None = None
    error: str | None = None


class StepHandler:
    """
    Handles execution of individual agent steps.
    
    Responsibilities:
    - Execute tool calls via ToolRegistry
    - Process special/meta tool results
    - Generate tool call records
    
    This class is designed to be stateless regarding agent workflow
    state, receiving only what it needs per call.
    """
    
    def __init__(
        self,
        tools: ToolRegistry,
        on_tool_call: "Callable[[ToolCall], None] | None" = None,
    ):
        """
        Initialize the step handler.
        
        Args:
            tools: Tool registry for looking up and executing tools
            on_tool_call: Optional callback for tool call notifications
        """
        self.tools = tools
        self._on_tool_call = on_tool_call
    
    async def execute_tool_call(
        self,
        tool_call_request: Any,
        max_output_chars: int = 10000,
    ) -> ToolCall:
        """
        Execute a single tool call and return the ToolCall record.
        
        Args:
            tool_call_request: Tool call request from LLM (has id, name, arguments)
            max_output_chars: Max chars before adding summarization reminder
            
        Returns:
            ToolCall with results populated
        """
        tool = self.tools.get(tool_call_request.name)
        
        tool_call = ToolCall(
            id=tool_call_request.id,
            tool_name=tool_call_request.name,
            input=tool_call_request.arguments,
        )
        
        if tool is None:
            tool_call.raw_output = f"Error: Tool '{tool_call_request.name}' not found"
            tool_call.success = False
            return tool_call
        
        try:
            # Execute the tool
            result: ToolResult = await tool.execute(**tool_call_request.arguments)
            
            tool_call.metadata = result.metadata
            tool_call.success = result.success
            tool_call.error = result.error

            # Ensure failures are visible to the model even if tool returned empty output.
            # Many tools return success=False, output="" and set error="...".
            if (not result.success) and (not (result.output or "").strip()) and result.error:
                tool_call.raw_output = f"Error: {result.error}"
            else:
                tool_call.raw_output = result.output
            
            # Note: Truncation instructions are added by get_truncated_output()
            # when the output exceeds max_chars during context rendering.
            # This ensures the AI sees the instruction within the char limit.
            
        except Exception as e:
            tool_call.raw_output = f"Error executing tool: {str(e)}"
            tool_call.success = False
            tool_call.error = str(e)
        
        # Invoke callback if provided
        if self._on_tool_call:
            self._on_tool_call(tool_call)
        
        return tool_call
    
    def process_special_tool(
        self,
        tool_call: ToolCall,
    ) -> SpecialToolResult | None:
        """
        Process special/meta tool results that affect agent workflow.
        
        Handles:
        - continue_analysis: Determines whether to continue or finish
        - transition_phase: Changes the workflow phase
        - branch_to_subtasks: Spawns parallel subagents
        
        Args:
            tool_call: The executed tool call to check
            
        Returns:
            SpecialToolResult if this was a special tool, None otherwise
        """
        from tempo.prompts.phases import Phase
        
        if tool_call.tool_name == "continue_analysis":
            if tool_call.metadata.get("continue"):
                # Agent wants to continue - loop back to HYPOTHESIZE for next testing cycle
                return SpecialToolResult(
                    tool_name="continue_analysis",
                    should_continue=True,
                    phase_transition=Phase.HYPOTHESIZE,
                )
            elif tool_call.metadata.get("finish"):
                # Agent is done
                return SpecialToolResult(
                    tool_name="continue_analysis",
                    should_continue=False,
                    findings={
                        "description": tool_call.metadata.get("findings", ""),
                        "reasoning": tool_call.metadata.get("reasoning", ""),
                    },
                )
        
        elif tool_call.tool_name == "transition_phase":
            phase_str = tool_call.input.get("phase", "")
            try:
                target_phase = Phase(phase_str)
                return SpecialToolResult(
                    tool_name="transition_phase",
                    phase_transition=target_phase,
                )
            except ValueError:
                return SpecialToolResult(
                    tool_name="transition_phase",
                    error=f"Invalid phase: {phase_str}",
                )
        
        elif tool_call.tool_name == "branch_to_subtasks":
            branch_id = tool_call.metadata.get("branch_id")
            if branch_id:
                return SpecialToolResult(
                    tool_name="branch_to_subtasks",
                    branch_id=branch_id,
                )
        
        elif tool_call.tool_name == "complete_recon":
            # Recon is complete - stop the agent
            if tool_call.metadata.get("recon_complete"):
                return SpecialToolResult(
                    tool_name="complete_recon",
                    should_continue=False,
                    findings={
                        "manifest_path": tool_call.metadata.get("manifest_path", ""),
                        "endpoint_count": tool_call.metadata.get("endpoint_count", 0),
                        "surface_count": tool_call.metadata.get("surface_count", 0),
                    },
                )
        
        elif tool_call.tool_name == "create_test_plan":
            # Test plan created - auto-transition to TEST phase
            if tool_call.metadata.get("plan_created"):
                return SpecialToolResult(
                    tool_name="create_test_plan",
                    phase_transition=Phase.TEST,
                )
        
        elif tool_call.tool_name == "complete_browser_task":
            # Browser task complete - stop the browser agent
            if tool_call.metadata.get("browser_task_complete"):
                return SpecialToolResult(
                    tool_name="complete_browser_task",
                    should_continue=False,
                    findings={
                        "findings": tool_call.metadata.get("findings", ""),
                        "success": tool_call.metadata.get("task_success", True),
                        "extracted_data": tool_call.metadata.get("extracted_data", ""),
                    },
                )
        
        return None
