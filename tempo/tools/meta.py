"""
Meta tools for agent control and subagent coordination.
"""

from typing import TYPE_CHECKING

from tempo.tools.base import Tool, ToolCategory, ToolResult, ToolSchema
from tempo.infra.protocols import (
    ContextSummarizer,
    BranchSpawner,
    FindingsUpdater,
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


# Alias for backward compatibility
SummarizeOutputTool = SummarizePreviousOutputTool


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


class FinalizeAnalysisTool(Tool):
    """Finalize the security analysis and generate the final report."""

    name = "finalize_analysis"
    description = """Finalize the security analysis and generate the final report.

    Call this tool when:
    - Sufficient reconnaissance has been performed
    - Attack surfaces have been adequately tested
    - You are ready to conclude the security assessment

    Provide:
    - final_report: Comprehensive summary of findings
    - executive_summary: Brief overview for stakeholders (optional)
    - risk_level: Overall risk assessment (optional)

    This tool saves the findings document and terminates the orchestrator."""
    category = ToolCategory.META

    def __init__(self, findings_updater: "FindingsUpdater"):
        """
        Initialize the finalize analysis tool.

        Args:
            findings_updater: Component implementing FindingsUpdater protocol
        """
        self.findings = findings_updater

    async def execute(
        self,
        final_report: str,
        executive_summary: str = "",
        risk_level: str = "medium",
        purpose: str = "",
    ) -> ToolResult:
        """
        Finalize the security analysis.

        Args:
            final_report: Comprehensive summary of findings
            executive_summary: Brief overview for stakeholders
            risk_level: Overall risk assessment (low, medium, high, critical)
            purpose: Why this tool is being called

        Returns:
            ToolResult with finalize_complete flag in metadata
        """
        # Validate risk level
        valid_risk_levels = {"low", "medium", "high", "critical"}
        if risk_level.lower() not in valid_risk_levels:
            risk_level = "medium"

        # Save the findings document if it has a save method
        try:
            if hasattr(self.findings, 'save') and hasattr(self.findings, 'file_path'):
                if self.findings.file_path:
                    self.findings.save()
        except Exception:
            pass  # Non-critical if save fails

        # Get final summary for output
        try:
            summary = self.findings.get_summary()
            findings_summary = (
                f"Total attack surfaces: {summary.get('total_surfaces', 0)} "
                f"({summary.get('tested_surfaces', 0)} tested)\n"
                f"Total findings: {summary.get('total_findings', 0)}\n"
                f"  Critical: {summary.get('findings_by_severity', {}).get('critical', 0)}\n"
                f"  High: {summary.get('findings_by_severity', {}).get('high', 0)}\n"
                f"  Medium: {summary.get('findings_by_severity', {}).get('medium', 0)}\n"
                f"  Low: {summary.get('findings_by_severity', {}).get('low', 0)}\n"
                f"  Info: {summary.get('findings_by_severity', {}).get('info', 0)}"
            )
        except Exception:
            findings_summary = "Unable to retrieve findings summary."

        output_parts = [
            "## Analysis Complete",
            "",
            f"**Risk Level**: {risk_level.upper()}",
            "",
            "### Findings Summary",
            findings_summary,
            "",
            "### Final Report",
            final_report,
        ]

        if executive_summary:
            output_parts.insert(3, "### Executive Summary")
            output_parts.insert(4, executive_summary)
            output_parts.insert(5, "")

        return ToolResult(
            success=True,
            output="\n".join(output_parts),
            metadata={
                "finalize_complete": True,
                "risk_level": risk_level.lower(),
                "executive_summary": executive_summary,
                "final_report": final_report,
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
                    "final_report": {
                        "type": "string",
                        "description": "Comprehensive summary of the security analysis findings.",
                    },
                    "executive_summary": {
                        "type": "string",
                        "description": "Brief overview suitable for stakeholders (optional).",
                    },
                    "risk_level": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "critical"],
                        "description": "Overall risk assessment for the target.",
                    },
                },
                "required": ["final_report"],
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

