"""
Test Subagent Definition.

A specialized subagent for testing tasks that tests attack surfaces and
documents security findings within the orchestrator architecture.
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
class TestSubagent(BaseAgentDefinition):
    """
    Testing subagent for testing attack surfaces.

    This subagent is designed to be dispatched by the orchestrator to perform
    focused testing tasks. It tests attack surfaces and documents security
    findings in the shared findings document.

    Features:
    - Testing tools (shell, file, browser)
    - Findings document integration (add_finding, mark_surface_tested)
    - Task completion signaling via complete_subtask
    - Fast model for efficient execution
    """

    _name = "test_subagent"
    _model = "openai/gpt-5.1"  # Capable model for security testing tasks

    def __init__(
        self,
        objective: str,
        findings: "FindingsUpdater",
        focus_area: str = "",
        **kwargs: Any,
    ):
        """
        Initialize the test subagent.

        Args:
            objective: The testing objective to accomplish
            findings: FindingsDocument instance for storing findings
            focus_area: Optional specific attack surfaces to test
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
        return "Testing subagent for testing attack surfaces and documenting findings"

    def create_tools(
        self,
        context: "ContextStore",
        container: "ContainerManager | None" = None,
        **kwargs: Any,
    ) -> "ToolRegistry":
        """
        Create the tool registry for the test subagent.

        Includes:
        - ShellTool: Command-line testing
        - FileReadTool/FileWriteTool: File system access
        - BrowserTaskTool: Web testing
        - AddFindingTool: Document vulnerabilities
        - MarkSurfaceTestedTool: Track testing progress
        - SummarizeOutputTool: Handle large outputs
        - CompleteSubtaskTool: Signal completion
        """
        from tempo.tools.registry import ToolRegistry
        from tempo.tools.shell import ShellTool
        from tempo.tools.filesystem import FileReadTool, FileWriteTool
        from tempo.tools.browser_task_tool import BrowserTaskTool
        from tempo.tools.headless_browser_tool import HeadlessBrowserTool
        from tempo.tools.findings_tools import (
            AddFindingTool,
            MarkSurfaceTestedTool,
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

        # Core testing tools
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
        tools.register(AddFindingTool(findings_updater=self.findings))
        tools.register(MarkSurfaceTestedTool(findings_updater=self.findings))

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
        Build the test subagent system prompt.

        Uses a focused prompt for testing.
        """
        # Get attack surfaces context
        attack_surfaces_context = self._get_attack_surfaces_context()

        # Pass scope if it's not a placeholder value
        scope_content = None
        if scope_description and scope_description not in DEFAULT_SCOPE_PLACEHOLDERS:
            scope_content = scope_description

        return prompts.build_test_subagent_prompt(
            tool_schemas=tool_schemas,
            objective=self.objective,
            attack_surfaces_context=attack_surfaces_context,
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
            "\nTest the assigned attack surfaces and document any findings. "
            "When complete, call `complete_subtask` with your summary."
        )

        return "\n".join(objective_parts)

    def _get_attack_surfaces_context(self) -> str:
        """Get detailed context including surfaces and prior findings."""
        try:
            summary = self.findings.get_summary()
            lines = [
                f"Target: {summary.get('target', 'Unknown')}",
                f"Attack Surfaces: {summary.get('total_surfaces', 0)} discovered, "
                f"{summary.get('tested_surfaces', 0)} tested",
                f"Findings: {summary.get('total_findings', 0)} total",
            ]

            # Include untested surfaces (primary focus for test agent)
            untested = self.findings.get_untested_surfaces()
            if untested:
                lines.append(f"\n### Untested Attack Surfaces ({len(untested)}) ###")
                for surface in untested[:15]:  # Limit to first 15
                    surface_id = getattr(surface, 'id', 'unknown')
                    surface_type = getattr(surface, 'surface_type', 'unknown')
                    url = getattr(surface, 'url', 'unknown')
                    priority = getattr(surface, 'priority', 'medium')
                    lines.append(f"- [{priority.upper()}] {surface_type}: {url} (ID: {surface_id})")

                if len(untested) > 15:
                    lines.append(f"... and {len(untested) - 15} more")
            else:
                lines.append("\n### Untested Attack Surfaces ###")
                lines.append("No untested attack surfaces available.")

            # Include all attack surfaces for full awareness
            all_surfaces = self.findings.get_all_surfaces()
            tested_surfaces = [s for s in all_surfaces if getattr(s, 'tested', False)]
            if tested_surfaces:
                lines.append(f"\n### Already Tested Surfaces ({len(tested_surfaces)}) ###")
                for surface in tested_surfaces[:10]:  # Limit to first 10
                    surface_id = getattr(surface, 'id', 'unknown')
                    surface_type = getattr(surface, 'surface_type', 'unknown')
                    url = getattr(surface, 'url', 'unknown')
                    lines.append(f"- [TESTED] {surface_type}: {url} (ID: {surface_id})")

                if len(tested_surfaces) > 10:
                    lines.append(f"... and {len(tested_surfaces) - 10} more")

            # Include existing findings with more detail
            all_findings = self.findings.get_all_findings()
            if all_findings:
                lines.append(f"\n### Security Findings ({len(all_findings)}) ###")
                for f in all_findings[:15]:  # Show more findings
                    fid = getattr(f, 'id', 'unknown')
                    title = getattr(f, 'title', 'No Title')
                    severity = getattr(f, 'severity', 'unknown')
                    status = getattr(f, 'status', 'unknown')
                    surface_id = getattr(f, 'surface_id', '')
                    location = f" (Surface: {surface_id})" if surface_id else ""
                    lines.append(f"- [{severity.upper()}] {title} ({status}){location}")

                if len(all_findings) > 15:
                    lines.append(f"... and {len(all_findings) - 15} more")

            return "\n".join(lines)
        except Exception:
            return "Unable to retrieve attack surfaces."
