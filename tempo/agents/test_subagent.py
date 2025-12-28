"""
Test Subagent Definition.

A specialized subagent for testing tasks that tests attack surfaces and
documents security findings within the orchestrator architecture.
"""

from typing import TYPE_CHECKING, Any

from tempo.agents.base import BaseAgentDefinition
from tempo.agents import register_agent
from tempo.prompts.phases import Phase

if TYPE_CHECKING:
    from tempo.context.store import ContextStore
    from tempo.infra.container import ContainerManager
    from tempo.agent.workflow import WorkflowManager
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
    _model = "openai/gpt-5-mini"  # Fast model for subagent tasks
    _initial_phase = Phase.TEST

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
        workflow: "WorkflowManager | None" = None,
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
        from tempo.tools.findings_tools import (
            AddFindingTool,
            MarkSurfaceTestedTool,
        )
        from tempo.tools.meta import SummarizeOutputTool
        from tempo.tools.complete_subtask import CompleteSubtaskTool

        tools = ToolRegistry()

        # Core testing tools
        tools.register(ShellTool(container_manager=container))
        tools.register(FileReadTool(container_manager=container))
        tools.register(FileWriteTool(container_manager=container))
        tools.register(BrowserTaskTool(
            container_manager=container,
            llm_client=None,  # Will create its own
        ))

        # Findings document tools - pass the findings reference
        tools.register(AddFindingTool(findings_updater=self.findings))
        tools.register(MarkSurfaceTestedTool(findings_updater=self.findings))

        # Meta tools
        tools.register(SummarizeOutputTool(context_store=context))
        tools.register(CompleteSubtaskTool())

        return tools

    def build_system_prompt(
        self,
        prompts: "PromptBuilder",
        tool_schemas: list[dict],
        scope_description: str,
    ) -> str:
        """
        Build the test subagent system prompt.

        Uses a focused prompt for testing without phase transitions.
        """
        # Get attack surfaces context
        attack_surfaces_context = self._get_attack_surfaces_context()

        return prompts.build_test_subagent_prompt(
            tool_schemas=tool_schemas,
            objective=self.objective,
            attack_surfaces_context=attack_surfaces_context,
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
        """Get a summary of untested attack surfaces."""
        try:
            untested = self.findings.get_untested_surfaces()
            if not untested:
                return "No untested attack surfaces available."

            lines = [f"**{len(untested)} untested attack surfaces:**"]
            for surface in untested[:10]:  # Limit to first 10
                surface_id = getattr(surface, 'id', 'unknown')
                surface_type = getattr(surface, 'surface_type', 'unknown')
                url = getattr(surface, 'url', 'unknown')
                priority = getattr(surface, 'priority', 'medium')
                lines.append(f"- [{priority.upper()}] {surface_type}: {url} (ID: {surface_id})")

            if len(untested) > 10:
                lines.append(f"... and {len(untested) - 10} more")

            return "\n".join(lines)
        except Exception:
            return "Unable to retrieve attack surfaces."
