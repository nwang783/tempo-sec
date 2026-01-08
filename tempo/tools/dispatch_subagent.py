"""
Dispatch Subagent Tool.

Tool for the orchestrator to dispatch specialized subagents (ReconSubagent, TestSubagent)
to perform focused tasks with access to the shared findings document.

Supports both single dispatch and parallel dispatch with concurrency control.
"""

import asyncio
import uuid
from typing import TYPE_CHECKING

from tempo.tools.base import Tool, ToolCategory, ToolResult, ToolSchema

if TYPE_CHECKING:
    from tempo.infra.container import ContainerManager
    from tempo.infra.protocols import FindingsUpdater, VisualizationObserver


class DispatchSubagentTool(Tool):
    """
    Dispatch specialized subagents to perform focused tasks.

    This tool allows the orchestrator to delegate work to ReconSubagent
    or TestSubagent, which operate with access to the shared findings document.

    Supports two modes:
    - Single dispatch: Pass subagent_type, objective, etc. directly
    - Parallel dispatch: Pass dispatch_requests array for concurrent execution
    """

    name = "dispatch_subagent"
    description = """Dispatch specialized subagents to perform focused tasks.

Available subagent types:
- "recon": ReconSubagent for discovering attack surfaces
- "test": TestSubagent for testing attack surfaces and finding vulnerabilities

The subagent will:
1. Execute with its own context and tools
2. Update the shared findings document
3. Return a summary of its work

**Single dispatch**: Pass subagent_type and objective directly.
**Parallel dispatch**: Pass dispatch_requests array to run multiple subagents concurrently."""
    category = ToolCategory.META

    def __init__(
        self,
        findings: "FindingsUpdater",
        container_manager: "ContainerManager | None" = None,
        visualization: "VisualizationObserver | None" = None,
        max_concurrent: int = 3,
        config: "Any" = None,
    ):
        """
        Initialize the dispatch subagent tool.

        Args:
            findings: FindingsDocument instance for shared state
            container_manager: Optional container for sandboxed execution
            visualization: Optional visualization observer for UI events
            max_concurrent: Maximum concurrent subagent dispatches (default: 3)
            config: Optional AgentConfig for browser settings and other configuration
        """
        self._findings = findings
        self._container_manager = container_manager
        self._visualization = visualization
        self._max_concurrent = max_concurrent
        self._config = config

    async def _run_subagent(
        self,
        subagent_type: str,
        objective: str,
        focus_area: str,
        scope: str = "",
    ) -> ToolResult:
        """
        Core subagent execution logic.

        Args:
            subagent_type: Type of subagent ("recon" or "test")
            objective: What the subagent should accomplish
            focus_area: Optional specific area to focus on
            scope: Optional scope constraints for the subagent

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

        # Generate unique ID for this subagent run
        subagent_id = str(uuid.uuid4())[:8]

        # Emit subagent start event for visualization
        if self._visualization and hasattr(self._visualization, 'on_subagent_start'):
            self._visualization.on_subagent_start(
                subagent_id=subagent_id,
                subagent_type=subagent_type,
                objective=objective,
                parent_id="orchestrator",
            )

        # Map to agent class
        if subagent_type == "recon":
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

        # Create child visualization collector for subagent (before creating tools)
        subagent_viz = None
        if self._visualization and hasattr(self._visualization, 'for_subagent'):
            subagent_viz = self._visualization.for_subagent(subagent_id)

        # Create tools for subagent (pass visualization and config)
        subagent_tools = subagent_def.create_tools(
            context=subagent_context,
            container=self._container_manager,
            visualization=subagent_viz,
            config=self._config,
        )

        # Create LLM client with subagent's model
        llm = LiteLLMClient(model=subagent_def.model)

        # Create agent config - use passed config if available to preserve browser settings
        if self._config:
            # Use passed config (preserves browser_headless, etc. from TOML)
            config = self._config
        else:
            config = AgentConfig(model=subagent_def.model)

        # Build prompts
        prompts = PromptBuilder()
        tool_schemas = subagent_tools.get_schemas()
        system_prompt = subagent_def.build_system_prompt(
            prompts=prompts,
            tool_schemas=tool_schemas,
            scope_description=scope if scope else "No specific scope constraints.",
        )

        # Add system prompt to context
        subagent_context.add_message(MessageRole.SYSTEM, system_prompt)

        # Register subagent context with server for viewing (if visualization available)
        if subagent_viz and hasattr(self._visualization, 'server'):
            self._visualization.server.register_subagent(
                subagent_id=subagent_id,
                context=subagent_context,
                metadata={
                    "type": subagent_type,
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
            )

            # Save findings after subagent completion using async-safe method if available
            if hasattr(self._findings, 'save_async'):
                try:
                    await self._findings.save_async()
                except Exception:
                    pass  # Non-critical if save fails
            elif hasattr(self._findings, 'save') and hasattr(self._findings, 'file_path'):
                if self._findings.file_path:
                    try:
                        self._findings.save()
                    except Exception:
                        pass  # Non-critical if save fails

            # Record agent invocation using async-safe method if available
            if hasattr(self._findings, 'add_agent_invocation_async'):
                await self._findings.add_agent_invocation_async(subagent_def.name)
            elif hasattr(self._findings, 'add_agent_invocation'):
                self._findings.add_agent_invocation(subagent_def.name)

            # Increment steps using async-safe method if available
            if hasattr(self._findings, 'increment_steps_async'):
                await self._findings.increment_steps_async(result.steps_taken)
            elif hasattr(self._findings, 'increment_steps'):
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
                                "subagent_id": subagent_id,
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
                        "subagent_id": subagent_id,
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
                        "subagent_id": subagent_id,
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
                        "subagent_id": subagent_id,
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
                metadata={
                    "subagent_id": subagent_id,
                    "subagent_type": subagent_type,
                },
            )

    async def _execute_parallel(
        self,
        dispatch_requests: list[dict],
    ) -> ToolResult:
        """
        Execute multiple subagents in parallel with concurrency control.

        Args:
            dispatch_requests: List of dicts with subagent_type, objective, focus_area, scope

        Returns:
            Aggregated ToolResult with all subagent outcomes
        """
        # Validate all requests first
        for i, req in enumerate(dispatch_requests):
            if not isinstance(req, dict):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Request {i} is not a dictionary: {type(req).__name__}",
                )
            subagent_type = req.get("subagent_type", "").lower()
            if subagent_type not in ("recon", "test"):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Request {i} has invalid subagent_type: {req.get('subagent_type')}. Must be 'recon' or 'test'.",
                )
            if not req.get("objective"):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Request {i} is missing required 'objective' field.",
                )

        # Create semaphore for concurrency limiting
        semaphore = asyncio.Semaphore(self._max_concurrent)

        async def run_with_semaphore(req: dict) -> ToolResult:
            async with semaphore:
                return await self._run_subagent(
                    subagent_type=req["subagent_type"].lower(),
                    objective=req["objective"],
                    focus_area=req.get("focus_area", ""),
                    scope=req.get("scope", ""),
                )

        # Execute all subagents in parallel with TaskGroup
        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(run_with_semaphore(req)) for req in dispatch_requests]

        # Collect results
        results = [task.result() for task in tasks]

        # Aggregate and return
        return self._aggregate_results(results)

    def _aggregate_results(self, results: list[ToolResult]) -> ToolResult:
        """
        Aggregate results from multiple parallel subagent executions.

        Args:
            results: List of ToolResult objects from individual subagents

        Returns:
            Aggregated ToolResult with combined summaries and metadata
        """
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        total_surfaces = sum(r.metadata.get("surfaces_added", 0) for r in successful)
        total_findings = sum(r.metadata.get("findings_added", 0) for r in successful)
        total_steps = sum(r.metadata.get("steps_taken", 0) for r in results)

        output_parts = [
            f"## Parallel Dispatch Results",
            f"",
            f"**Total subagents dispatched:** {len(results)}",
            f"**Successful:** {len(successful)}",
            f"**Failed:** {len(failed)}",
            f"**Total steps taken:** {total_steps}",
            f"**Total attack surfaces added:** {total_surfaces}",
            f"**Total findings added:** {total_findings}",
            f"",
        ]

        if successful:
            output_parts.append("### Successful Subagents")
            for i, r in enumerate(successful, 1):
                subagent_type = r.metadata.get("subagent_type", "unknown")
                summary = r.metadata.get("summary", "No summary")
                surfaces = r.metadata.get("surfaces_added", 0)
                findings = r.metadata.get("findings_added", 0)
                output_parts.append(
                    f"{i}. **{subagent_type}** - {summary} "
                    f"(surfaces: {surfaces}, findings: {findings})"
                )
            output_parts.append("")

        if failed:
            output_parts.append("### Failed Subagents")
            for i, r in enumerate(failed, 1):
                subagent_type = r.metadata.get("subagent_type", "unknown")
                error = r.error or "Unknown error"
                output_parts.append(f"{i}. **{subagent_type}** - Error: {error}")
            output_parts.append("")

        return ToolResult(
            success=len(failed) == 0,  # Only fully successful if no failures
            output="\n".join(output_parts),
            error=f"{len(failed)} subagent(s) failed" if failed else None,
            metadata={
                "total_dispatched": len(results),
                "successful_count": len(successful),
                "failed_count": len(failed),
                "total_steps": total_steps,
                "total_surfaces_added": total_surfaces,
                "total_findings_added": total_findings,
                "subagent_results": [
                    {
                        "subagent_id": r.metadata.get("subagent_id"),
                        "subagent_type": r.metadata.get("subagent_type"),
                        "success": r.success,
                        "summary": r.metadata.get("summary", ""),
                        "surfaces_added": r.metadata.get("surfaces_added", 0),
                        "findings_added": r.metadata.get("findings_added", 0),
                        "steps_taken": r.metadata.get("steps_taken", 0),
                        "error": r.error,
                    }
                    for r in results
                ],
            },
        )

    async def execute(
        self,
        subagent_type: str | None = None,
        objective: str | None = None,
        focus_area: str = "",
        scope: str = "",
        dispatch_requests: list[dict] | None = None,
        purpose: str = "",
    ) -> ToolResult:
        """
        Dispatch subagent(s) to perform tasks.

        Two modes of operation:
        - Single dispatch: Pass subagent_type and objective
        - Parallel dispatch: Pass dispatch_requests array

        Args:
            subagent_type: Type of subagent ("recon" or "test") - for single dispatch
            objective: What the subagent should accomplish - for single dispatch
            focus_area: Optional specific area to focus on - for single dispatch
            scope: Optional scope constraints - for single dispatch
            dispatch_requests: List of dicts for parallel dispatch, each with:
                - subagent_type: "recon" or "test"
                - objective: What to accomplish
                - focus_area: Optional focus (default: "")
                - scope: Optional scope constraints (default: "")
            purpose: Why this tool is being called

        Returns:
            ToolResult with the subagent's findings
        """
        # Determine mode based on which parameters are provided
        if dispatch_requests is not None:
            # Parallel dispatch mode
            if not dispatch_requests:
                return ToolResult(
                    success=False,
                    output="",
                    error="dispatch_requests must be a non-empty list.",
                )
            return await self._execute_parallel(dispatch_requests)

        # Single dispatch mode - validate required parameters
        if not subagent_type:
            return ToolResult(
                success=False,
                output="",
                error="subagent_type is required for single dispatch. Use dispatch_requests for parallel dispatch.",
            )
        if not objective:
            return ToolResult(
                success=False,
                output="",
                error="objective is required for single dispatch.",
            )

        # Validate subagent type
        subagent_type_lower = subagent_type.lower()
        if subagent_type_lower not in ("recon", "test"):
            return ToolResult(
                success=False,
                output="",
                error=f"Invalid subagent_type: {subagent_type}. Must be 'recon' or 'test'.",
            )

        return await self._run_subagent(
            subagent_type=subagent_type_lower,
            objective=objective,
            focus_area=focus_area,
            scope=scope,
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
                        "description": "Type of subagent (for single dispatch): 'recon' for reconnaissance, 'test' for vulnerability testing. Must be 'recon' or 'test'.",
                        "enum": ["recon", "test"],
                    },
                    "objective": {
                        "type": "string",
                        "description": "What the subagent should accomplish (for single dispatch)",
                    },
                    "focus_area": {
                        "type": "string",
                        "description": "Optional specific area or surfaces to focus on (for single dispatch)",
                    },
                    "scope": {
                        "type": "string",
                        "description": "Optional scope constraints (e.g., 'Only test /api/* endpoints')",
                    },
                    "dispatch_requests": {
                        "type": "array",
                        "description": "For parallel dispatch: array of subagent requests to execute concurrently. Each item must have 'subagent_type' (recon/test) and 'objective', optionally 'focus_area' and 'scope'.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "subagent_type": {
                                    "type": "string",
                                    "description": "Type of subagent: 'recon' or 'test'",
                                    "enum": ["recon", "test"],
                                },
                                "objective": {
                                    "type": "string",
                                    "description": "What the subagent should accomplish",
                                },
                                "focus_area": {
                                    "type": "string",
                                    "description": "Optional focus area",
                                },
                                "scope": {
                                    "type": "string",
                                    "description": "Optional scope constraints",
                                },
                            },
                            "required": ["subagent_type", "objective"],
                        },
                    },
                    "purpose": {
                        "type": "string",
                        "description": "Brief explanation of why this dispatch is needed",
                    },
                },
                "required": [],
            },
        )
