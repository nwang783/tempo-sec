"""
Complete Subtask Tool.

Tool for subagents to signal subtask completion and report results back to the orchestrator.
"""

from tempo.tools.base import Tool, ToolCategory, ToolResult, ToolSchema


class CompleteSubtaskTool(Tool):
    """
    Signal subtask completion and report findings back to the orchestrator.

    This is the terminal tool for subagents (ReconSubagent, TestSubagent) - when called,
    the subagent stops and returns results to the parent orchestrator.
    """

    name = "complete_subtask"
    description = """Signal that your subtask is complete and report results.

    Call this when you have finished your assigned objective. Provide:
    - summary: A concise summary of what you accomplished
    - surfaces_added: Number of attack surfaces you added (for recon subagents)
    - findings_added: Number of security findings you added (for test subagents)
    - notes: Any additional observations or recommendations

    Your results will be returned to the orchestrator for integration."""
    category = ToolCategory.META

    async def execute(
        self,
        summary: str,
        surfaces_added: int | str = 0,
        findings_added: int | str = 0,
        notes: str = "",
        purpose: str = "",
    ) -> ToolResult:
        """
        Complete the subtask and report results.

        Args:
            summary: Concise summary of what was accomplished
            surfaces_added: Number of attack surfaces added (recon subagents)
            findings_added: Number of security findings added (test subagents)
            notes: Additional observations or recommendations
            purpose: Why this tool is being called

        Returns:
            ToolResult with completion metadata
        """
        # Coerce to int (LLM may pass as string)
        surfaces_added = int(surfaces_added)
        findings_added = int(findings_added)
        
        output_parts = [f"Subtask completed: {summary}"]

        if surfaces_added > 0:
            output_parts.append(f"\nAttack surfaces added: {surfaces_added}")

        if findings_added > 0:
            output_parts.append(f"\nFindings added: {findings_added}")

        if notes:
            output_parts.append(f"\nNotes: {notes}")

        return ToolResult(
            success=True,
            output="\n".join(output_parts),
            metadata={
                "subtask_complete": True,
                "summary": summary,
                "surfaces_added": surfaces_added,
                "findings_added": findings_added,
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
                        "description": "Concise summary of what you accomplished during the subtask",
                    },
                    "surfaces_added": {
                        "type": "integer",
                        "description": "Number of attack surfaces added to the findings document (default: 0)",
                        "default": 0,
                    },
                    "findings_added": {
                        "type": "integer",
                        "description": "Number of security findings added to the findings document (default: 0)",
                        "default": 0,
                    },
                    "notes": {
                        "type": "string",
                        "description": "Additional observations or recommendations (optional)",
                        "default": "",
                    },
                },
                "required": ["summary"],
            },
        )
