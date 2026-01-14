"""
Browser Task Tool.

Tool for parent agents to delegate browser tasks to a specialized browser agent.
"""

from typing import TYPE_CHECKING

from tempo.tools.base import Tool, ToolCategory, ToolResult, ToolSchema

if TYPE_CHECKING:
    from tempo.infra.container import ContainerManager
    from tempo.infra.llm import LLMClient
    from tempo.infra.protocols import VisualizationObserver, FindingsUpdater


class BrowserTaskTool(Tool):
    """
    Delegate a browser task to a specialized browser agent.
    
    This tool allows parent agents (Recon, TestCycle) to offload
    browser-based tasks to a dedicated browser agent that runs
    autonomously and returns findings.
    
    Features:
    - State persistence (load/save browser sessions)
    - Scope constraints propagation
    - Visualization event propagation (UI visibility)
    """
    
    name = "browser_task"
    description = (
        "Execute a browser-based task using a specialized browser agent. "
        "Use this for web browsing, form filling, clicking, and page analysis. "
        "Supports state persistence (reuse logged-in sessions) and scope constraints. "
        "The browser agent will complete the task and return its findings."
    )
    category = ToolCategory.BROWSING
    
    def __init__(
        self,
        container_manager: "ContainerManager | None" = None,
        llm_client: "LLMClient | None" = None,
        visualization_collector: "VisualizationObserver | None" = None,
        findings_updater: "FindingsUpdater | None" = None,
        headless: bool = True,
    ):
        """
        Initialize the browser task tool.

        Args:
            container_manager: Container for sandboxed browser execution
            llm_client: LLM client for the browser agent (if None, creates new one)
            visualization_collector: Collector for UI event propagation
            findings_updater: Optional findings document for prior work context
            headless: Whether to run browser in headless mode (default: True)
        """
        self._container_manager = container_manager
        self._llm_client = llm_client
        self._visualization_collector = visualization_collector
        self._findings_updater = findings_updater
        self._headless = headless
    
    async def execute(
        self,
        task: str,
        url: str = "",
        scope: str = "",
        use_browser_use_llm: bool = False,
        purpose: str = "",
        **kwargs,
    ) -> ToolResult:
        """
        Execute a browser task via the browser-use agent.

        Args:
            task: Description of what the browser agent should accomplish
            url: Optional starting URL (if provided, agent navigates there first)
            scope: Optional scope constraints for the browser agent (not yet supported by browser-use)
            use_browser_use_llm: Use browser-use's ChatBrowserUse model (if True) or OpenRouter gpt-5.1 (if False)
            purpose: Why this browser task is being executed
            **kwargs: Additional arguments (ignored)

        Returns:
            ToolResult with the browser agent's findings
        """
        import uuid
        import os
        from tempo.agents.browser import BrowserAgent

        # Fixed step limit for browser agent
        max_steps = 50

        # Get email config from environment
        agent_email = os.getenv("TEMPO_AGENT_EMAIL")
        imap_password = os.getenv("TEMPO_IMAP_PASSWORD")
        imap_config = None
        if imap_password:
            imap_config = {
                "host": os.getenv("TEMPO_IMAP_HOST", "imap.gmail.com"),
                "port": 993,
                "password": imap_password,
            }

        # Create browser agent definition
        browser_agent_def = BrowserAgent(
            task=task,
            url=url if url else None,
            scope=scope if scope else None,
            headless=self._headless,
            findings=self._findings_updater,
            agent_email=agent_email,
            imap_config=imap_config,
            use_browser_use_llm=use_browser_use_llm,
        )

        # Create browser-use agent with custom tools
        browser_use_agent, browser, combined_tools = browser_agent_def.create_browser_use_agent(
            container=self._container_manager,
        )

        # --- Visualization bridge for browser-use actions ---
        # browser-use executes browser interactions via combined_tools.registry.execute_action(...)
        # The Tempo visualization UI expects events via VisualizationCollector.on_step/on_tool_call_start/on_tool_call.
        # We wrap execute_action so each browser-use action shows up as a "tool call" under the browser subagent.
        browser_step_counter = 0
        # Pre-generate browser_id so the closure can capture it
        browser_id = f"browser_{uuid.uuid4().hex[:8]}" if self._visualization_collector else None
        if self._visualization_collector and hasattr(combined_tools, "registry"):
            try:
                import json
                import time

                original_execute_action = combined_tools.registry.execute_action

                async def _execute_action_with_viz(*args, **kwargs):
                    nonlocal browser_step_counter
                    browser_step_counter += 1

                    # Registry.execute_action signature uses (action_name, params, ...)
                    action_name = kwargs.get("action_name") if "action_name" in kwargs else (args[0] if args else "")
                    params = kwargs.get("params") if "params" in kwargs else (args[1] if len(args) > 1 else {})

                    # Ensure we have a stable subagent id for routing in the UI
                    subagent_id = browser_id or "browser"
                    frame_id = subagent_id

                    # Emit a step first so the UI has a step_number before the tool call arrives
                    if hasattr(self._visualization_collector, "on_step"):
                        self._visualization_collector.on_step(
                            {
                                "step_number": browser_step_counter,
                                "phase": None,
                                "error": None,
                                "should_continue": True,
                                "llm_content": None,
                                "usage": {},
                                "subagent_id": subagent_id,
                            },
                            frame_id,
                        )

                    # Emit tool_call_start for immediate UI feedback
                    tool_call_id = f"{subagent_id}:{browser_step_counter}:{action_name}"
                    if hasattr(self._visualization_collector, "on_tool_call_start"):
                        self._visualization_collector.on_tool_call_start(
                            {
                                "id": tool_call_id,
                                "tool_name": str(action_name),
                                "input": params if isinstance(params, dict) else {},
                                "subagent_id": subagent_id,
                            },
                            frame_id,
                        )

                    start = time.time()
                    try:
                        result = await original_execute_action(*args, **kwargs)
                        duration_ms = int((time.time() - start) * 1000)

                        # Normalize result for display
                        raw_output_obj = result
                        if hasattr(result, "model_dump"):
                            raw_output_obj = result.model_dump()
                        raw_output = (
                            json.dumps(raw_output_obj, ensure_ascii=False, default=str)
                            if not isinstance(raw_output_obj, str)
                            else raw_output_obj
                        )

                        error = getattr(result, "error", None)
                        success = not bool(error)

                        if hasattr(self._visualization_collector, "on_tool_call"):
                            self._visualization_collector.on_tool_call(
                                {
                                    "id": tool_call_id,
                                    "tool_name": str(action_name),
                                    "input": params if isinstance(params, dict) else {},
                                    "raw_output": raw_output,
                                    "summary": None,
                                    "success": success,
                                    "error": str(error) if error else None,
                                    "duration_ms": duration_ms,
                                    "metadata": {"browser_use": True},
                                    "subagent_id": subagent_id,
                                },
                                frame_id,
                            )

                        return result
                    except Exception as e:
                        duration_ms = int((time.time() - start) * 1000)
                        if hasattr(self._visualization_collector, "on_tool_call"):
                            self._visualization_collector.on_tool_call(
                                {
                                    "id": tool_call_id,
                                    "tool_name": str(action_name),
                                    "input": params if isinstance(params, dict) else {},
                                    "raw_output": "",
                                    "summary": None,
                                    "success": False,
                                    "error": str(e),
                                    "duration_ms": duration_ms,
                                    "metadata": {"browser_use": True},
                                    "subagent_id": subagent_id,
                                },
                                frame_id,
                            )
                        raise

                combined_tools.registry.execute_action = _execute_action_with_viz  # type: ignore[assignment]
            except Exception:
                # If instrumentation fails, do not break the browser task.
                pass

        # Emit visualization events if collector available
        if self._visualization_collector:
            # Get parent subagent ID from the collector (if it's a child collector)
            parent_id = getattr(self._visualization_collector, "_subagent_id", None) or "orchestrator"

            # Emit browser agent start event
            if hasattr(self._visualization_collector, "on_subagent_start"):
                self._visualization_collector.on_subagent_start(
                    subagent_id=browser_id,
                    subagent_type="browser",
                    objective=task,
                    parent_id=parent_id,
                )

        try:
            # Run browser-use agent
            history = await browser_use_agent.run(max_steps=max_steps)

            # Extract results from history
            steps_taken = len(history.history) if hasattr(history, "history") else 0

            # browser-use histories expose helpers as methods; call them if callable
            final_result = None
            if hasattr(history, "final_result") and callable(getattr(history, "final_result")):
                final_result = history.final_result()

            extracted_content = None
            if hasattr(history, "extracted_content"):
                maybe = getattr(history, "extracted_content")
                extracted_content = maybe() if callable(maybe) else maybe

            # Determine success: prefer explicit final-result semantics, otherwise look for errors
            success = False
            if final_result:
                success = True
            else:
                # Best-effort: if any action result reports an error, treat as failure
                try:
                    all_results = getattr(history, "all_results", None) or getattr(history, "history", None)
                    if all_results:
                        has_error = any(getattr(r, "error", None) for r in all_results)
                        success = not has_error
                except Exception:
                    success = False

            output = f"Browser task {'completed' if success else 'failed'} in {steps_taken} steps."

            if final_result:
                output += f"\n\nResult: {final_result}"
            if extracted_content:
                output += f"\n\nExtracted content: {extracted_content}"

            # Emit subagent finish event
            if self._visualization_collector and hasattr(self._visualization_collector, "on_subagent_finish"):
                self._visualization_collector.on_subagent_finish(
                    subagent_id=browser_id or "browser",
                    success=success,
                    summary=output[:200],
                    findings_count=0,
                    surfaces_count=0,
                )

            return ToolResult(
                success=success,
                output=output,
                metadata={
                    "steps_taken": steps_taken,
                },
            )

        except Exception as e:
            # Emit subagent finish event for failure
            if self._visualization_collector and hasattr(self._visualization_collector, "on_subagent_finish"):
                self._visualization_collector.on_subagent_finish(
                    subagent_id=browser_id or "browser",
                    success=False,
                    summary=str(e)[:200],
                    findings_count=0,
                    surfaces_count=0,
                )

            return ToolResult(
                success=False,
                output=f"Browser task failed: {str(e)}",
                error=str(e),
            )
        
        finally:
            # Clean up browser resources
            try:
                await browser.close()
            except Exception:
                # Ignore cleanup errors
                pass
    
    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": (
                            "Description of the browser task to accomplish. "
                            "Be specific about what information to find or what actions to perform."
                        ),
                    },
                    "url": {
                        "type": "string",
                        "description": "Starting URL to navigate to (optional)",
                        "default": "",
                    },
                    "scope": {
                        "type": "string",
                        "description": (
                            "Optional scope constraints for the browser agent. "
                            "Describe allowed/disallowed domains or actions."
                        ),
                        "default": "",
                    },
                    "use_browser_use_llm": {
                        "type": "boolean",
                        "description": (
                            "Use browser-use's ChatBrowserUse model (true) or OpenRouter gpt-5.1 (false). "
                            "Default: false (use OpenRouter)."
                        ),
                        "default": False,
                    },
                },
                "required": ["task"],
            },
        )
