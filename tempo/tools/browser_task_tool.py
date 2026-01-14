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
        state_name: str = "",
        save_state_as: str = "",
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
            state_name: Optional name of saved state to load (e.g., 'admin_session')
            save_state_as: Optional name to save state as after task completion
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
        from tempo.infra.browser_state import BrowserStateManager
        from tempo.tools.browser_use_state import BrowserUseStateTools

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
            state_name=state_name if state_name else None,
            save_state_as=save_state_as if save_state_as else None,
            scope=scope if scope else None,
            headless=self._headless,
            findings=self._findings_updater,
            agent_email=agent_email,
            imap_config=imap_config,
            use_browser_use_llm=use_browser_use_llm,
        )

        # Create browser-use agent with custom tools
        state_manager = BrowserStateManager(ttl_days=7)
        browser_use_agent, browser, combined_tools = browser_agent_def.create_browser_use_agent(
            container=self._container_manager,
            state_manager=state_manager,
        )

        # Handle state loading if specified
        if state_name:
            try:
                state = await state_manager.load(state_name)
                if state:
                    state_tools = BrowserUseStateTools(browser, state_manager)
                    await state_tools.restore_state(state)
            except Exception as e:
                return ToolResult(
                    success=False,
                    output=f"Failed to load state '{state_name}': {str(e)}",
                    error=str(e),
                )

        # Emit visualization events if collector available
        browser_id = None
        if self._visualization_collector:
            browser_id = f"browser_{uuid.uuid4().hex[:8]}"

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

            # Handle state saving if specified
            if save_state_as:
                try:
                    state_tools = BrowserUseStateTools(browser, state_manager)
                    captured_state = await state_tools.capture_state(
                        name=save_state_as,
                        description=f"State saved after browser task: {task[:100]}"
                    )
                    await state_manager.save(captured_state)
                except Exception as e:
                    # Log error but don't fail the task
                    pass

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
                    "state_loaded": state_name if state_name else None,
                    "state_saved": save_state_as if save_state_as else None,
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
                    "state_name": {
                        "type": "string",
                        "description": (
                            "Optional name of saved browser state to load "
                            "(e.g., 'admin_session'). The browser will restore "
                            "cookies and storage from this state."
                        ),
                        "default": "",
                    },
                    "save_state_as": {
                        "type": "string",
                        "description": (
                            "Optional name to save browser state as after task completion. "
                            "Use this to persist authenticated sessions for later reuse."
                        ),
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
