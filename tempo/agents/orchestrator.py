"""
OrchestratorAgent Definition.

The top-level agent that coordinates security analysis by dispatching
specialized subagents and managing a shared findings document.
"""

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from tempo.agents.base import BaseAgentDefinition
from tempo.agents import register_agent

if TYPE_CHECKING:
    from tempo.context.store import ContextStore
    from tempo.infra.container import ContainerManager
    from tempo.tools.registry import ToolRegistry
    from tempo.prompts.builder import PromptBuilder
    from tempo.findings.document import FindingsDocument


@register_agent
class OrchestratorAgent(BaseAgentDefinition):
    """
    Orchestrator agent that coordinates security analysis.

    This is the top-level agent for comprehensive security assessments.
    It strategically dispatches specialized subagents (ReconSubagent, TestSubagent)
    and manages a shared FindingsDocument that persists across all agent invocations.

    Features:
    - Strategic planning and decision-making using the smartest model
    - Dynamic subagent dispatch based on analysis needs
    - Shared findings document for persistent knowledge
    - Comprehensive final reporting

    Usage:
        orchestrator = OrchestratorAgent(
            target="https://example.com",
            findings_path="./findings/example.yaml",
            max_iterations=10,
        )
    """

    _name = "orchestrator"
    _model = "openai/gpt-5.1"  # Smartest model for strategic planning

    def __init__(
        self,
        target: str = "See scope file",
        findings_path: str | None = None,
        max_iterations: int = 10,
        scope_content: str | None = None,
        **kwargs: Any,
    ):
        """
        Initialize the orchestrator agent.

        Args:
            target: Legacy target field (deprecated, use scope_content instead)
            findings_path: Optional path to findings document.
                          If provided and exists: loads existing document.
                          If provided but doesn't exist: creates new at that path.
                          If None: auto-generates path based on timestamp.
            max_iterations: Maximum orchestrator iterations (default: 10)
            scope_content: Scope file content containing target(s) and constraints.
                          This is injected directly into the system prompt.
            **kwargs: Ignored additional args (for compatibility)
        """
        self.target = target
        self._findings_path = findings_path
        self._max_iterations = max_iterations
        self._scope_content = scope_content
        self._findings: "FindingsDocument | None" = None
        self._session_id = kwargs.get("session_id", "")

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "Security analysis orchestrator that coordinates subagents and manages findings"

    @property
    def findings(self) -> "FindingsDocument":
        """
        Lazy-load or create the findings document.

        Loading strategy:
        1. If findings_path provided and file exists: load it
        2. If findings_path provided but doesn't exist: create new at that path
        3. If no findings_path: auto-generate path from target
        """
        if self._findings is None:
            from tempo.findings.document import FindingsDocument

            if self._findings_path:
                path = Path(self._findings_path)
                
                # Handle directory paths - look for .yaml file with same name
                if path.is_dir():
                    # If directory given, look for {dirname}.yaml in parent
                    yaml_path = path.parent / f"{path.name}.yaml"
                    if yaml_path.exists():
                        path = yaml_path
                    else:
                        # Create new findings file alongside directory
                        self._findings = FindingsDocument(
                            target=self.target,
                            file_path=str(yaml_path),
                        )
                        return self._findings
                
                if path.exists():
                    # Load existing document
                    self._findings = FindingsDocument.load(str(path))
                else:
                    # Create new document at specified path
                    # Add .yaml extension if missing
                    if path.suffix != ".yaml":
                        path = path.with_suffix(".yaml")
                    path.parent.mkdir(parents=True, exist_ok=True)
                    self._findings = FindingsDocument(
                        target=self.target,
                        file_path=str(path),
                    )
            else:
                # Auto-generate path from target
                safe_target = self._make_safe_filename(self.target)
                findings_dir = Path("./findings")
                findings_dir.mkdir(parents=True, exist_ok=True)
                auto_path = findings_dir / f"{safe_target}.yaml"
                self._findings = FindingsDocument(
                    target=self.target,
                    file_path=str(auto_path),
                )

        return self._findings

    def _make_safe_filename(self, target: str) -> str:
        """Convert target to a safe filename."""
        # Remove protocol
        safe = re.sub(r'^https?://', '', target)
        # Replace unsafe characters
        safe = re.sub(r'[^\w\-.]', '_', safe)
        # Remove trailing underscores/dots
        safe = safe.strip('_.')
        # Limit length
        if len(safe) > 50:
            safe = safe[:50]
        return safe or "unknown_target"

    def create_tools(
        self,
        context: "ContextStore",
        container: "ContainerManager | None" = None,
        **kwargs: Any,
    ) -> "ToolRegistry":
        """
        Create the tool registry for the orchestrator.

        Includes:
        - Core tools: shell, filesystem (for direct analysis if needed)
        - Subagent dispatch: dispatch_subagents
        - Findings management: read_findings, add_finding, add_attack_surface
        - Meta tools: summarize_previous_tool_output, finalize_analysis
        """
        from tempo.tools.registry import ToolRegistry
        from tempo.tools.shell import ShellTool
        from tempo.tools.filesystem import FileReadTool, FileWriteTool
        from tempo.tools.dispatch_subagents import DispatchSubagentsTool
        from tempo.tools.findings_tools import (
            ReadFindingsTool,
            AddFindingTool,
            AddAttackSurfaceTool,
        )
        from tempo.tools.meta import (
            SummarizeOutputTool,
            FinalizeAnalysisTool,
        )

        tools = ToolRegistry()

        # Extract visualization collector and config from kwargs (passed from run.py)
        visualization = kwargs.get("visualization")
        config = kwargs.get("config")
        max_concurrent = getattr(config, "max_concurrent_subagents", 3) if config else 3

        # Core tools - orchestrator can do lightweight analysis directly
        tools.register(ShellTool(container_manager=container))
        tools.register(FileReadTool(container_manager=container))
        tools.register(FileWriteTool(container_manager=container))

        # Subagent dispatch - combined single/parallel dispatch tool
        tools.register(DispatchSubagentsTool(
            findings=self.findings,
            container_manager=container,
            visualization=visualization,
            max_concurrent=max_concurrent,
            config=config,
        ))

        # Findings management tools
        tools.register(ReadFindingsTool(findings_updater=self.findings))
        tools.register(AddFindingTool(findings_updater=self.findings))
        tools.register(AddAttackSurfaceTool(findings_updater=self.findings))

        # Meta tools
        tools.register(SummarizeOutputTool(context_store=context))
        tools.register(FinalizeAnalysisTool(findings_updater=self.findings))

        return tools

    def build_system_prompt(
        self,
        prompts: "PromptBuilder",
        tool_schemas: list[dict],
        scope_description: str,
    ) -> str:
        """
        Build the orchestrator system prompt.

        Uses the orchestrator-specific prompt template that emphasizes
        strategic planning and subagent coordination.
        """
        # Get current findings summary
        findings_summary = self._get_findings_summary()

        return prompts.build_orchestrator_prompt(
            tool_schemas=tool_schemas,
            target=self.target,
            findings_summary=findings_summary,
            scope_content=self._scope_content,
        )

    def build_objective(self, target: str | None = None, **kwargs: Any) -> str:
        """
        Build the orchestrator objective.

        Args:
            target: Optional target override (uses self.target if not provided)
            **kwargs: Ignored

        Returns:
            Formatted objective string
        """
        target = target or self.target
        findings_summary = self._get_findings_summary()

        objective_parts = [
            f"## Security Analysis Orchestration",
            f"",
            f"**Target:** {target}",
            f"",
            f"### Current State",
            findings_summary if findings_summary else "No findings yet. Start with reconnaissance.",
            f"",
            f"### Your Task",
            f"Coordinate a comprehensive security analysis of the target.",
            f"",
            f"1. Start by calling `read_findings` to understand the current state",
            f"2. Dispatch subagents as needed (`dispatch_subagents`)",
            f"3. Review results and determine next steps",
            f"4. Continue until adequate coverage is achieved",
            f"5. Call `finalize_analysis` to generate the final report",
            f"",
            f"**Max Iterations:** {self._max_iterations}",
        ]

        return "\n".join(objective_parts)

    def _get_findings_summary(self) -> str:
        """Get a formatted summary of the current findings document state."""
        try:
            summary = self.findings.get_summary()
            total_surfaces = summary.get('total_surfaces', 0)
            tested_surfaces = summary.get('tested_surfaces', 0)
            total_findings = summary.get('total_findings', 0)
            findings_by_severity = summary.get('findings_by_severity', {})

            lines = [
                f"**Target:** {summary.get('target', self.target)}",
                f"",
                f"**Attack Surfaces:** {total_surfaces} discovered, {tested_surfaces} tested",
                f"**Findings:** {total_findings} total",
            ]

            if total_findings > 0:
                severity_parts = []
                for level in ['critical', 'high', 'medium', 'low', 'info']:
                    count = findings_by_severity.get(level, 0)
                    if count > 0:
                        severity_parts.append(f"{level.capitalize()}: {count}")
                if severity_parts:
                    lines.append(f"  - {', '.join(severity_parts)}")

            agents = summary.get('agents_invoked', [])
            if agents:
                lines.append(f"**Agents invoked:** {', '.join(agents)}")

            steps = summary.get('total_steps', 0)
            if steps > 0:
                lines.append(f"**Total steps taken:** {steps}")

            return "\n".join(lines)

        except Exception:
            return "Unable to load findings summary."
