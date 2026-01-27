"""
Recon Subagent Definition.

A specialized subagent for reconnaissance tasks that discovers and documents
attack surfaces within the orchestrator architecture.
"""

from typing import TYPE_CHECKING, Any

from tempo.agents.base import BaseAgentDefinition
from tempo.agents import register_agent

from tempo.infra.protocols import DEFAULT_SCOPE_PLACEHOLDERS

if TYPE_CHECKING:
    from tempo.context.store import ContextStore
    from tempo.infra.container import ContainerManager
    from tempo.tools.registry import ToolRegistry
    from tempo.prompts.builder import PromptBuilder
    from tempo.infra.protocols import FindingsUpdater


@register_agent
class ReconSubagent(BaseAgentDefinition):
    """
    Reconnaissance subagent for discovering attack surfaces.

    This subagent is designed to be dispatched by the orchestrator to perform
    focused reconnaissance tasks. It discovers attack surfaces and documents
    them in the shared findings document.

    Features:
    - Focused reconnaissance tools (shell, file, browser)
    - Findings document integration (add_attack_surface, update_recon_summary)
    - Task completion signaling via complete_subtask
    - Fast model for efficient execution
    """

    _name = "recon_subagent"
    _model = "openai/gpt-5-mini"  # Fast model for subagent tasks

    def __init__(
        self,
        objective: str,
        findings: "FindingsUpdater",
        focus_area: str = "",
        **kwargs: Any,
    ):
        """
        Initialize the recon subagent.

        Args:
            objective: The reconnaissance objective to accomplish
            findings: FindingsDocument instance for storing discoveries
            focus_area: Optional specific area to focus reconnaissance
            **kwargs: Ignored additional args
        """
        self.objective = objective
        self.findings = findings
        self.focus_area = focus_area

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "Reconnaissance subagent for discovering attack surfaces"

    def create_tools(
        self,
        context: "ContextStore",
        container: "ContainerManager | None" = None,
        **kwargs: Any,
    ) -> "ToolRegistry":
        """
        Create the tool registry for the recon subagent.

        Includes:
        - ShellTool: Command-line reconnaissance
        - FileReadTool/FileWriteTool: File system access
        - BrowserTaskTool: Web exploration
        - AddAttackSurfaceTool: Document discoveries
        - UpdateReconSummaryTool: Update summary statistics
        - SummarizeOutputTool: Handle large outputs
        - CompleteSubtaskTool: Signal completion
        """
        from tempo.tools.registry import ToolRegistry
        from tempo.tools.shell import ShellTool
        from tempo.tools.filesystem import FileReadTool, FileWriteTool
        from tempo.tools.browser_task_tool import BrowserTaskTool
        from tempo.tools.headless_browser_tool import HeadlessBrowserTool
        from tempo.tools.findings_tools import (
            AddAttackSurfaceTool,
            UpdateReconSummaryTool,
        )
        from tempo.tools.meta import SummarizeOutputTool
        from tempo.tools.complete_subtask import CompleteSubtaskTool

        # Extract visualization collector and config from kwargs
        visualization = kwargs.get("visualization")
        config = kwargs.get("config")
        
        # Get headless setting from config (default: True)
        headless = True
        if config and hasattr(config, "browser_headless"):
            headless = config.browser_headless

        tools = ToolRegistry()

        # Core reconnaissance tools
        tools.register(ShellTool(container_manager=container))
        tools.register(FileReadTool(container_manager=container))
        tools.register(FileWriteTool(container_manager=container))
        
        # Headless browser (preferred - faster, non-visual)
        tools.register(HeadlessBrowserTool(
            container_manager=container,
            findings_updater=self.findings,
        ))
        
        # Visual browser (fallback for complex visual tasks)
        tools.register(BrowserTaskTool(
            container_manager=container,
            visualization_collector=visualization,
            findings_updater=self.findings,
            headless=headless,
        ))

        # Findings document tools - pass the findings reference
        tools.register(AddAttackSurfaceTool(findings_updater=self.findings))
        tools.register(UpdateReconSummaryTool(findings_updater=self.findings))

        # Meta tools
        tools.register(SummarizeOutputTool(context_store=context))
        tools.register(CompleteSubtaskTool(findings=self.findings))

        return tools

    def build_system_prompt(
        self,
        prompts: "PromptBuilder",
        tool_schemas: list[dict],
        scope_description: str,
    ) -> str:
        """
        Build the recon subagent system prompt.

        Uses a focused prompt for reconnaissance.
        """
        # Get findings context summary
        findings_context = self._get_findings_context()

        # Pass scope if it's not a placeholder value
        scope_content = None
        if scope_description and scope_description not in DEFAULT_SCOPE_PLACEHOLDERS:
            scope_content = scope_description

        return prompts.build_recon_subagent_prompt(
            tool_schemas=tool_schemas,
            objective=self.objective,
            findings_context=findings_context,
            focus_area=self.focus_area,
            scope_content=scope_content,
        )

    def build_objective(self, target: str | None = None, **kwargs: Any) -> str:
        """
        Build the subagent objective.

        Args:
            target: Ignored (uses objective from init)
            **kwargs: Ignored

        Returns:
            Formatted objective with focus area
        """
        objective_parts = [f"**Objective**: {self.objective}"]

        if self.focus_area:
            objective_parts.append(f"\n**Focus Area**: {self.focus_area}")

        objective_parts.append(
            "\nDiscover attack surfaces and document them using the available tools. "
            "When complete, call `complete_subtask` with your summary."
        )

        return "\n".join(objective_parts)

    def _get_findings_context(self) -> str:
        """Get detailed findings context including all surfaces and findings."""
        try:
            summary = self.findings.get_summary()
            lines = [
                f"Target: {summary.get('target', 'Unknown')}",
                f"Attack Surfaces: {summary.get('total_surfaces', 0)} discovered, "
                f"{summary.get('tested_surfaces', 0)} tested",
                f"Findings: {summary.get('total_findings', 0)} total",
            ]

            # Include all attack surfaces
            all_surfaces = self.findings.get_all_surfaces()
            if all_surfaces:
                lines.append("\n### Attack Surfaces Discovered ###")
                for s in all_surfaces:
                    sid = getattr(s, 'id', 'unknown')
                    stype = getattr(s, 'surface_type', 'unknown')
                    url = getattr(s, 'url', 'unknown')
                    tested = getattr(s, 'tested', False)
                    status_str = "TESTED" if tested else "UNTESTED"
                    lines.append(f"- [{status_str}] {stype}: {url} | ID: {sid}")

            # Include all findings
            all_findings = self.findings.get_all_findings()
            if all_findings:
                lines.append("\n### Findings Recorded ###")
                for f in all_findings:
                    fid = getattr(f, 'id', 'unknown')
                    title = getattr(f, 'title', 'No Title')
                    severity = getattr(f, 'severity', 'unknown')
                    status = getattr(f, 'status', 'unknown')
                    lines.append(f"- [{severity.upper()}] {title} ({status}) | ID: {fid}")

            return "\n".join(lines)
        except Exception:
            return "No existing findings document"
