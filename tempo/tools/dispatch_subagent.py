"""
Dispatch Subagent Tool.

Tool for the orchestrator to dispatch specialized subagents (ReconSubagent, TestSubagent)
to perform focused tasks with access to the shared findings document.
"""

from typing import TYPE_CHECKING

from tempo.tools.base import Tool, ToolCategory, ToolResult, ToolSchema

if TYPE_CHECKING:
    from tempo.infra.container import ContainerManager
    from tempo.infra.protocols import FindingsUpdater, VisualizationObserver


class DispatchSubagentTool(Tool):
    """
    Dispatch a specialized subagent to perform a focused task.

    This tool allows the orchestrator to delegate work to ReconSubagent
    or TestSubagent, which operate with access to the shared findings document.
    """

    name = "dispatch_subagent"
    description = """Dispatch a specialized subagent to perform a focused task.

    Available subagent types:
    - "recon": ReconSubagent for discovering attack surfaces
    - "test": TestSubagent for testing attack surfaces and finding vulnerabilities

    The subagent will:
    1. Execute with its own context and tools
    2. Update the shared findings document
    3. Return a summary of its work

    Use this to parallelize work or focus on specific objectives."""
    category = ToolCategory.META

    def __init__(
        self,
        findings: "FindingsUpdater",
        container_manager: "ContainerManager | None" = None,
        visualization: "VisualizationObserver | None" = None,
    ):
        """
        Initialize the dispatch subagent tool.

        Args:
            findings: FindingsDocument instance for shared state
            container_manager: Optional container for sandboxed execution
            visualization: Optional visualization observer for UI events
        """
        self._findings = findings
        self._container_manager = container_manager
        self._visualization = visualization

    async def execute(
        self,
        subagent_type: str,
        objective: str,
        focus_area: str = "",
        max_steps: int | str = 50,
        purpose: str = "",
    ) -> ToolResult:
        """
        Dispatch a subagent to perform a task.

        Args:
            subagent_type: Type of subagent ("recon" or "test")
            objective: What the subagent should accomplish
            focus_area: Optional specific area to focus on
            max_steps: Maximum steps for the subagent (default: 50)
            purpose: Why this tool is being called

        Returns:
            ToolResult with the subagent's findings
        """
        from tempo.agents.recon_subagent import ReconSubagent
        from tempo.agents.test_subagent import TestSubagent
        from tempo.agent.config import AgentConfig
        from tempo.agent.runner import Agent
        from tempo.context.store import ContextStore
        from tempo.context.frame import MessageRole
        from tempo.prompts.builder import PromptBuilder
        from tempo.infra.llm import LiteLLMClient

        # Coerce max_steps to int (LLM may pass as string)
        max_steps = int(max_steps)
        
        # Validate subagent type
        subagent_type_lower = subagent_type.lower()
        if subagent_type_lower not in ("recon", "test"):
            return ToolResult(
                success=False,
                output="",
                error=f"Invalid subagent_type: {subagent_type}. Must be 'recon' or 'test'.",
            )

        # Generate unique ID for this subagent run
        import uuid
        subagent_id = str(uuid.uuid4())[:8]
        
        # Emit subagent start event for visualization
        if self._visualization and hasattr(self._visualization, 'on_subagent_start'):
            self._visualization.on_subagent_start(
                subagent_id=subagent_id,
                subagent_type=subagent_type_lower,
                objective=objective,
                parent_id="orchestrator",
            )

        # Map to agent class
        if subagent_type_lower == "recon":
            subagent_def = ReconSubagent(
                objective=objective,
                findings=self._findings,
                focus_area=focus_area,
            )
        else:  # test
            subagent_def = TestSubagent(
                objective=objective,
                findings=self._findings,
                focus_area=focus_area,
            )

        # Create isolated context for subagent
        subagent_context = ContextStore()

        # Create tools for subagent
        subagent_tools = subagent_def.create_tools(
            context=subagent_context,
            container=self._container_manager,
        )

        # Create LLM client with subagent's model
        llm = LiteLLMClient(model=subagent_def.model)

        # Create agent config
        config = AgentConfig(
            model=subagent_def.model,
            max_total_steps=max_steps,
        )

        # Build prompts
        prompts = PromptBuilder()
        tool_schemas = subagent_tools.get_schemas()
        system_prompt = subagent_def.build_system_prompt(
            prompts=prompts,
            tool_schemas=tool_schemas,
            scope_description="Subagent task",
        )

        # Add system prompt to context
        subagent_context.add_message(MessageRole.SYSTEM, system_prompt)

        # Create child collector for subagent (enables real-time visualization)
        subagent_viz = None
        if self._visualization and hasattr(self._visualization, 'for_subagent'):
            subagent_viz = self._visualization.for_subagent(subagent_id)
            # Register subagent context with server for viewing
            if hasattr(self._visualization, 'server'):
                self._visualization.server.register_subagent(
                    subagent_id=subagent_id,
                    context=subagent_context,
                    metadata={
                        "type": subagent_type_lower,
                        "objective": objective,
                    },
                )

        # Create and run subagent
        subagent = Agent(
            config=config,
            llm=llm,
            tools=subagent_tools,
            context=subagent_context,
            visualization_collector=subagent_viz,
        )

        # Build objective
        subagent_objective = subagent_def.build_objective()

        try:
            # Run subagent
            result = await subagent.run(
                objective=subagent_objective,
                initial_phase=subagent_def.initial_phase,
                max_steps=max_steps,
            )

            # Save findings after subagent completion (if the findings document supports it)
            if hasattr(self._findings, 'save') and hasattr(self._findings, 'file_path'):
                if self._findings.file_path:
                    try:
                        self._findings.save()
                    except Exception:
                        pass  # Non-critical if save fails

            # Record agent invocation
            if hasattr(self._findings, 'add_agent_invocation'):
                self._findings.add_agent_invocation(subagent_def.name)

            # Increment steps
            if hasattr(self._findings, 'increment_steps'):
                self._findings.increment_steps(result.steps_taken)

            # Extract results from subagent findings
            if result.success and result.findings:
                # Look for subtask_complete findings
                for finding in result.findings:
                    if finding.get("summary"):
                        summary = finding.get("summary", "")
                        surfaces_added = finding.get("surfaces_added", 0)
                        findings_added = finding.get("findings_added", 0)
                        notes = finding.get("notes", "")

                        output_parts = [
                            f"Subagent ({subagent_type}) completed in {result.steps_taken} steps.",
                            f"\nSummary: {summary}",
                        ]

                        if surfaces_added > 0:
                            output_parts.append(f"\nAttack surfaces added: {surfaces_added}")

                        if findings_added > 0:
                            output_parts.append(f"\nFindings added: {findings_added}")

                        if notes:
                            output_parts.append(f"\nNotes: {notes}")

                        # Emit subagent finish event
                        if self._visualization and hasattr(self._visualization, 'on_subagent_finish'):
                            self._visualization.on_subagent_finish(
                                subagent_id=subagent_id,
                                success=True,
                                summary=summary,
                                findings_count=findings_added,
                                surfaces_count=surfaces_added,
                            )

                        return ToolResult(
                            success=True,
                            output="\n".join(output_parts),
                            metadata={
                                "subagent_type": subagent_type,
                                "steps_taken": result.steps_taken,
                                "summary": summary,
                                "surfaces_added": surfaces_added,
                                "findings_added": findings_added,
                                "notes": notes,
                            },
                        )

                # No structured findings, return generic success
                return ToolResult(
                    success=True,
                    output=f"Subagent ({subagent_type}) completed in {result.steps_taken} steps. "
                           f"Findings: {result.findings}",
                    metadata={
                        "subagent_type": subagent_type,
                        "steps_taken": result.steps_taken,
                        "raw_findings": result.findings,
                    },
                )

            elif result.success:
                # Emit subagent finish event
                if self._visualization and hasattr(self._visualization, 'on_subagent_finish'):
                    self._visualization.on_subagent_finish(
                        subagent_id=subagent_id,
                        success=True,
                        summary="Completed with no specific findings",
                        findings_count=0,
                        surfaces_count=0,
                    )
                return ToolResult(
                    success=True,
                    output=f"Subagent ({subagent_type}) completed in {result.steps_taken} steps (no specific findings).",
                    metadata={
                        "subagent_type": subagent_type,
                        "steps_taken": result.steps_taken,
                    },
                )

            else:
                # Emit subagent finish event for failure
                if self._visualization and hasattr(self._visualization, 'on_subagent_finish'):
                    self._visualization.on_subagent_finish(
                        subagent_id=subagent_id,
                        success=False,
                        summary=result.error or "Unknown error",
                        findings_count=0,
                        surfaces_count=0,
                    )
                return ToolResult(
                    success=False,
                    output=f"Subagent ({subagent_type}) failed: {result.error or 'Unknown error'}",
                    error=result.error,
                    metadata={
                        "subagent_type": subagent_type,
                        "steps_taken": result.steps_taken,
                    },
                )

        except Exception as e:
            # Emit subagent finish event for exception
            if self._visualization and hasattr(self._visualization, 'on_subagent_finish'):
                self._visualization.on_subagent_finish(
                    subagent_id=subagent_id,
                    success=False,
                    summary=str(e),
                    findings_count=0,
                    surfaces_count=0,
                )
            return ToolResult(
                success=False,
                output=f"Error running {subagent_type} subagent: {str(e)}",
                error=str(e),
            )

    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "subagent_type": {
                        "type": "string",
                        "enum": ["recon", "test"],
                        "description": "Type of subagent to dispatch: 'recon' for reconnaissance, 'test' for vulnerability testing",
                    },
                    "objective": {
                        "type": "string",
                        "description": "What the subagent should accomplish",
                    },
                    "focus_area": {
                        "type": "string",
                        "description": "Optional specific area or surfaces to focus on",
                        "default": "",
                    },
                    "max_steps": {
                        "type": "integer",
                        "description": "Maximum steps for the subagent (default: 50)",
                        "default": 50,
                    },
                },
                "required": ["subagent_type", "objective"],
            },
        )
