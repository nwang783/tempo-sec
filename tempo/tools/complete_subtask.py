"""
Complete Subtask Tool.

Tool for subagents to signal subtask completion and report results back to the orchestrator.
"""

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from tempo.tools.base import Tool, ToolCategory, ToolResult, ToolSchema

if TYPE_CHECKING:
    from tempo.infra.protocols import FindingsUpdater


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
    - limitations: Any blockers, incomplete work, or areas needing follow-up

    Your results will be returned to the orchestrator for integration."""
    category = ToolCategory.META

    def __init__(self, findings: "FindingsUpdater | None" = None):
        """
        Initialize the complete subtask tool.
        
        Args:
            findings: Optional FindingsDocument for getting target path
        """
        self._findings = findings

    def _save_limitations_file(self, limitations: str, summary: str) -> str | None:
        """
        Append limitations to the shared limitations file.
        
        Args:
            limitations: The limitations text to save
            summary: Summary of what was accomplished (for context)
            
        Returns:
            Path to the limitations file, or None if not saved
        """
        if not limitations:
            return None
        
        # Get target from findings for directory structure
        target = "unknown_target"
        if self._findings and hasattr(self._findings, "target"):
            target = self._findings.target
        elif self._findings and hasattr(self._findings, "get_summary"):
            try:
                summary_dict = self._findings.get_summary()
                target = summary_dict.get("target", target)
            except Exception:
                pass
        
        # Sanitize target for filename
        safe_target = re.sub(r'^https?://', '', target)
        safe_target = re.sub(r'[^\w\-.]', '_', safe_target)
        safe_target = safe_target.strip('_.')[:50] or "unknown_target"
        
        # Create directory and file
        limitations_dir = Path("findings") / safe_target
        limitations_dir.mkdir(parents=True, exist_ok=True)
        limitations_path = limitations_dir / "limitations.md"
        
        # Build entry
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        summary_preview = summary[:100] + "..." if len(summary) > 100 else summary
        entry = f"\n## Subtask: {summary_preview}\n"
        entry += f"**Timestamp:** {timestamp}\n\n"
        entry += f"{limitations}\n"
        entry += "\n---\n"
        
        try:
            # Create header if file doesn't exist
            if not limitations_path.exists():
                header = "# Limitations & Incomplete Work\n\n"
                header += "This file documents limitations, blockers, and incomplete work "
                header += "encountered by agents during the security assessment.\n"
                with open(limitations_path, "w") as f:
                    f.write(header)
            
            with open(limitations_path, "a") as f:
                f.write(entry)
            
            return str(limitations_path)
        except Exception:
            return None

    async def execute(
        self,
        summary: str,
        surfaces_added: int | str = 0,
        findings_added: int | str = 0,
        notes: str = "",
        limitations: str = "",
        purpose: str = "",
    ) -> ToolResult:
        """
        Complete the subtask and report results.

        Args:
            summary: Concise summary of what was accomplished
            surfaces_added: Number of attack surfaces added (recon subagents)
            findings_added: Number of security findings added (test subagents)
            notes: Additional observations or recommendations
            limitations: Blockers, incomplete work, or areas needing follow-up
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

        if limitations:
            output_parts.append(f"\nLimitations: {limitations}")
            
        # Save limitations to file if present
        limitations_path = None
        if limitations:
            limitations_path = self._save_limitations_file(limitations, summary)
            if limitations_path:
                output_parts.append(f"\n(Limitations saved to {limitations_path})")

        return ToolResult(
            success=True,
            output="\n".join(output_parts),
            metadata={
                "subtask_complete": True,
                "summary": summary,
                "surfaces_added": surfaces_added,
                "findings_added": findings_added,
                "notes": notes,
                "limitations": limitations,
                "limitations_path": limitations_path,
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
                    "limitations": {
                        "type": "string",
                        "description": (
                            "Any limitations, blockers, or incomplete work encountered. "
                            "Examples: pages that couldn't be accessed, features requiring auth, "
                            "areas needing deeper investigation, tools that failed."
                        ),
                        "default": "",
                    },
                },
                "required": ["summary"],
            },
        )

