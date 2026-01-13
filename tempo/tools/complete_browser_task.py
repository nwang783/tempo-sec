"""
Complete Browser Task Tool.

Tool for the browser agent to signal task completion and report findings.
"""

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from tempo.tools.base import Tool, ToolCategory, ToolResult, ToolSchema

if TYPE_CHECKING:
    from tempo.infra.protocols import FindingsUpdater


class CompleteBrowserTaskTool(Tool):
    """
    Signal browser task completion and report findings.
    
    This is the terminal tool for the browser agent - when called,
    the browser agent stops and returns findings to the parent agent.
    """
    
    name = "complete_browser_task"
    description = "Signal that the browser task is complete and report findings back to the caller"
    category = ToolCategory.META

    def __init__(self, findings: "FindingsUpdater | None" = None):
        """
        Initialize the complete browser task tool.
        
        Args:
            findings: Optional FindingsDocument for getting target path
        """
        self._findings = findings

    def _save_limitations_file(self, limitations: str, findings_summary: str) -> str | None:
        """
        Append limitations to the shared limitations file.
        
        Args:
            limitations: The limitations text to save
            findings_summary: Summary of findings (for context)
            
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
        summary_preview = findings_summary[:100] + "..." if len(findings_summary) > 100 else findings_summary
        entry = f"\n## Browser Task: {summary_preview}\n"
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
        findings: str,
        success: bool = True,
        extracted_data: str = "",
        limitations: str = "",
        purpose: str = "",
        **kwargs,
    ) -> ToolResult:
        """
        Complete the browser task and report findings.
        
        Args:
            findings: Summary of what was found/accomplished during browsing
            success: Whether the task was completed successfully
            extracted_data: Any specific data extracted (URLs, text, form values, etc.)
            limitations: Any blockers or incomplete work encountered
            
        Returns:
            ToolResult with completion metadata
        """
        output_parts = [f"Browser task completed: {findings}"]
        
        if extracted_data:
            output_parts.append(f"\nExtracted data:\n{extracted_data}")
        
        if not success:
            output_parts.append("\n[Task marked as unsuccessful]")
        
        if limitations:
            output_parts.append(f"\nLimitations: {limitations}")
            
        # Save limitations to file if present
        limitations_path = None
        if limitations:
            limitations_path = self._save_limitations_file(limitations, findings)
            if limitations_path:
                output_parts.append(f"\n(Limitations saved to {limitations_path})")
        
        return ToolResult(
            success=True,  # Tool execution succeeded even if task didn't
            output="\n".join(output_parts),
            metadata={
                "browser_task_complete": True,
                "findings": findings,
                "task_success": success,
                "extracted_data": extracted_data,
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
                    "limitations": {
                        "type": "string",
                        "description": (
                            "Any limitations encountered during browsing. "
                            "Examples: pages blocked by auth, JavaScript errors, "
                            "elements not found, timeouts, areas needing manual testing."
                        ),
                        "default": "",
                    },
                },
                "required": ["findings"],
            },
        )

