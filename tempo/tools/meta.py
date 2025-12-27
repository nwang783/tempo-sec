"""
Meta tools for agent control, phase transitions, and branching.
"""

from typing import TYPE_CHECKING

from tempo.tools.base import Tool, ToolCategory, ToolResult, ToolSchema
from tempo.infra.protocols import (
    PhaseTransitioner,
    ContextSummarizer,
    BranchSpawner,
)


class TransitionPhaseTool(Tool):
    """Transition the agent to a new workflow phase."""
    
    name = "transition_phase"
    description = """Move to the next workflow phase (recon → hypothesize → test → reflect).
    
    Use this tool when you have completed work in the current phase and are ready to proceed.
    This does NOT end the analysis - it advances to the next phase of investigation.
    
    Call this BEFORE calling complete_analysis."""
    category = ToolCategory.META
    
    def __init__(self, workflow_manager: PhaseTransitioner):
        """
        Initialize the transition phase tool.
        
        Args:
            workflow_manager: Any component implementing PhaseTransitioner protocol
        """
        self.workflow = workflow_manager
        
    async def execute(
        self,
        phase: str,
        justification: str,
        purpose: str = "",
    ) -> ToolResult:
        """
        Transition to a new phase.
        
        Args:
            phase: Target phase (recon, hypothesize, test, reflect)
            justification: Why you are moving to this phase
            purpose: A one-sentence summary of why this tool is being called
            
        Returns:
            ToolResult indicating success/failure
        """
        from tempo.infra.phases import Phase
        from tempo.agent.workflow import WorkflowError
        
        try:
            target_phase = Phase(phase.lower())
            self.workflow.transition(target_phase)
            return ToolResult(
                success=True,
                output=f"Switched to {target_phase.value} phase.",
                metadata={"phase": target_phase.value},
            )
        except ValueError:
            return ToolResult(
                success=False,
                output="",
                error=f"Invalid phase: {phase}. Valid phases: recon, hypothesize, test, reflect",
            )
        except WorkflowError as e:
            return ToolResult(
                success=False,
                output="",
                error=str(e),
            )
            
    def get_schema(self) -> ToolSchema:
        """Return the JSON schema for this tool's parameters."""
        from tempo.infra.phases import Phase
        
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "phase": {
                        "type": "string",
                        "enum": [p.value for p in Phase],
                        "description": "The target phase",
                    },
                    "justification": {
                        "type": "string",
                        "description": "Why you are moving to this phase",
                    },
                },
                "required": ["phase", "justification"],
            },
        )


class SummarizePreviousOutputTool(Tool):
    """Summarize the previous tool output using LLM with conversation context."""
    
    name = "summarize_previous_tool_output"
    description = "Summarize the previous tool's output to save context. Call this when prompted after a large tool output."
    category = ToolCategory.META
    
    def __init__(self, context_store: ContextSummarizer):
        """
        Initialize the summarize previous output tool.
        
        Args:
            context_store: Any component implementing ContextSummarizer protocol
        """
        self.context = context_store
        
    async def execute(
        self,
        purpose: str = "",
    ) -> ToolResult:
        """
        Summarize the pending tool call's output using Gemini Flash.
        
        No arguments needed - automatically targets the first unsummarized tool call
        and uses LLM with conversation context to generate a substantive summary.
        
        Args:
            purpose: A one-sentence summary of why this tool is being called
            
        Returns:
            ToolResult indicating success/failure with the generated summary
        """
        from tempo.infra.llm import LiteLLMClient
        
        # Get the pending tool call ID
        pending_id = self.context.get_pending_summarization_id()
        if not pending_id:
            return ToolResult(
                success=False,
                output="",
                error="No tool output pending summarization.",
            )
        
        # Get the tool call
        tool_call = self.context.find_tool_call(pending_id)
        if not tool_call:
            return ToolResult(
                success=False,
                output="",
                error=f"Tool call not found: {pending_id}",
            )
        
        # Get recent conversation context
        recent_messages = self.context.get_recent_messages(limit=5)
        context_str = "\n".join([
            f"{m.role.value.upper()}: {m.content[:500]}..." 
            if len(m.content) > 500 else f"{m.role.value.upper()}: {m.content}"
            for m in recent_messages
        ])
        
        # Build summarization prompt with context
        import json
        tool_input_str = json.dumps(tool_call.input, indent=2) if isinstance(tool_call.input, dict) else str(tool_call.input)
        
        # Limit output to ~10k tokens (~40k chars) to avoid rate limits
        MAX_CHARS_FOR_SUMMARIZER = 40000
        raw_output = tool_call.raw_output or ""
        output_truncated = len(raw_output) > MAX_CHARS_FOR_SUMMARIZER
        output_for_summary = raw_output[:MAX_CHARS_FOR_SUMMARIZER]
        
        truncation_note = ""
        if output_truncated:
            truncation_note = f"\n\n[NOTE: Output truncated to first {MAX_CHARS_FOR_SUMMARIZER:,} chars. Full output is {len(raw_output):,} chars. Use view_tool_output to see remaining content.]"
        
        prompt = f"""Summarize the following tool output concisely. Focus on information relevant to the current conversation context.

## Recent Conversation Context:
{context_str}

## Tool: {tool_call.tool_name}
## Input: {tool_input_str}

## Output to Summarize:
{output_for_summary}{truncation_note}

## Instructions:
1. Extract key findings relevant to the conversation context
2. Note any errors or issues
3. Identify actionable information
4. Keep summary under 200 words
{f"5. Note that only the first {MAX_CHARS_FOR_SUMMARIZER:,} chars were summarized" if output_truncated else ""}

Provide ONLY the summary, no preamble."""

        try:
            # Use Gemini Flash for efficient summarization
            flash_client = LiteLLMClient(model="gemini/gemini-3-flash-preview")
            response = await flash_client.complete(
                messages=[{"role": "user", "content": prompt}],
            )
            
            summary = response.content.strip()
            
            # Store the summary
            self.context.summarize_tool_call(pending_id, summary)
            
            return ToolResult(
                success=True,
                output=f"Summarized: {summary}",
                metadata={"summarized_tool_id": pending_id},
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Summarization failed: {str(e)}",
            )

    def get_schema(self) -> ToolSchema:
        """Return the JSON schema for this tool's parameters."""
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {},  # No arguments!
            },
        )


# Keep old name as alias for backward compatibility
SummarizeOutputTool = SummarizePreviousOutputTool



class ContinueAnalysisTool(Tool):
    """Decide whether to continue or finish the security analysis."""
    
    name = "continue_analysis"
    description = """Decide whether to continue or finish the security analysis.
    
    You MUST call this tool after entering the REFLECT phase.
    Analyze your findings, then decide:
    
    - should_continue=true: More investigation is needed → transitions back to RECON
    - should_continue=false: Analysis is complete → ends execution with findings
    
    This is the ONLY tool available in the REFLECT phase."""
    category = ToolCategory.META
    
    async def execute(
        self,
        should_continue: bool,
        reasoning: str,
        findings: str = "",
        purpose: str = "",
    ) -> ToolResult:
        """
        Decide whether to continue or finish analysis.
        
        Args:
            should_continue: True to continue with more investigation, False to finish
            reasoning: Explanation of why you are continuing or finishing
            findings: Summary of findings (required if finishing)
            purpose: A one-sentence summary of why this tool is being called
            
        Returns:
            ToolResult with continue or finish flag in metadata
        """
        if should_continue:
            return ToolResult(
                success=True,
                output="Continuing analysis.",
                metadata={"continue": True, "reasoning": reasoning},
            )
        else:
            if not findings:
                return ToolResult(
                    success=False,
                    output="",
                    error="When finishing analysis (should_continue=false), you must provide findings.",
                )
            return ToolResult(
                success=True,
                output="Analysis complete.",
                metadata={"finish": True, "findings": findings, "reasoning": reasoning},
            )
            
    def get_schema(self) -> ToolSchema:
        """Return the JSON schema for this tool's parameters."""
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "should_continue": {
                        "type": "boolean",
                        "description": "True to continue investigating, False to finish and report findings.",
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Explanation of why you are continuing or finishing.",
                    },
                    "findings": {
                        "type": "string",
                        "description": "Summary of findings. Required when should_continue is false.",
                    },
                },
                "required": ["should_continue", "reasoning"],
            },
        )


# Keep FinishTaskTool as an alias for backward compatibility
FinishTaskTool = ContinueAnalysisTool


class BranchToSubtasksTool(Tool):
    """Spawn parallel subagents to work on subtasks."""
    
    name = "branch_to_subtasks"
    description = """Spawn parallel subagents to investigate subtasks. Use this for:
    - Investigating multiple hypotheses in parallel
    - Research tasks that can be done independently
    - Any work that should result in a summary
    
    Each subtask will be handled by a clone of yourself. When all subtasks complete,
    their summaries will be merged and returned to you."""
    category = ToolCategory.META
    
    def __init__(self, branch_coordinator: BranchSpawner):
        """
        Initialize the branch tool.
        
        Args:
            branch_coordinator: Any component implementing BranchSpawner protocol
        """
        self.coordinator = branch_coordinator
        
    async def execute(
        self,
        subtasks: list[str],
        purpose: str = "",
    ) -> ToolResult:
        """
        Spawn subagents for each subtask.
        
        Args:
            subtasks: List of subtask objectives
            purpose: A one-sentence summary of why this tool is being called
            
        Returns:
            ToolResult with branch_id for tracking
        """
        if not subtasks:
            return ToolResult(
                success=False,
                output="",
                error="At least one subtask is required",
            )
        
        branch_id = await self.coordinator.spawn_subtasks(subtasks)
        return ToolResult(
            success=True,
            output=f"Spawned {len(subtasks)} subagents. Waiting for results...",
            metadata={"branch_id": branch_id, "pending": True, "subtask_count": len(subtasks)},
        )
        
    def get_schema(self) -> ToolSchema:
        """Return the JSON schema for this tool's parameters."""
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "subtasks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of subtask objectives for subagents to work on",
                    },
                },
                "required": ["subtasks"],
            },
        )


class FinishSubtaskTool(Tool):
    """Signal completion of a subtask (used by subagents)."""
    
    name = "finish_subtask"
    description = """Signal that your subtask is complete. Provide a summary of:
    - What you investigated
    - What actions you took  
    - Key findings or results
    
    Your summary will be merged with other subagent results and returned
    to the main agent."""
    category = ToolCategory.META
    
    async def execute(
        self,
        summary: str,
        findings: list[dict] | None = None,
        purpose: str = "",
    ) -> ToolResult:
        """
        Report subtask completion.
        
        Args:
            summary: Summary of what you did and found
            findings: Optional structured findings
            purpose: A one-sentence summary of why this tool is being called
            
        Returns:
            ToolResult with subtask_complete flag
        """
        return ToolResult(
            success=True,
            output="Subtask complete.",
            metadata={
                "subtask_complete": True,
                "summary": summary,
                "findings": findings or [],
            },
        )
        
    def get_schema(self) -> ToolSchema:
        """Return the JSON schema for this tool's parameters."""
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Summary of what you did and found",
                    },
                    "findings": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string"},
                                "description": {"type": "string"},
                                "severity": {
                                    "type": "string",
                                    "enum": ["low", "medium", "high", "critical"],
                                },
                            },
                        },
                        "description": "Optional structured findings",
                    },
                },
                "required": ["summary"],
            },
        )

