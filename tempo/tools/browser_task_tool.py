"""
Browser Task Tool.

Tool for parent agents to delegate browser tasks to a specialized browser agent.
"""

from typing import TYPE_CHECKING

from tempo.tools.base import Tool, ToolCategory, ToolResult, ToolSchema

if TYPE_CHECKING:
    from tempo.infra.container import ContainerManager
    from tempo.infra.llm import LLMClient
    from tempo.infra.protocols import VisualizationObserver


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
        headless: bool = True,
    ):
        """
        Initialize the browser task tool.
        
        Args:
            container_manager: Container for sandboxed browser execution
            llm_client: LLM client for the browser agent (if None, creates new one)
            visualization_collector: Collector for UI event propagation
            headless: Whether to run browser in headless mode (default: True)
        """
        self._container_manager = container_manager
        self._llm_client = llm_client
        self._visualization_collector = visualization_collector
        self._headless = headless
    
    async def execute(
        self,
        task: str,
        url: str = "",
        state_name: str = "",
        save_state_as: str = "",
        scope: str = "",
        max_steps: int | str = 10,
        purpose: str = "",
        **kwargs,
    ) -> ToolResult:
        """
        Execute a browser task via the browser agent.
        
        Args:
            task: Description of what the browser agent should accomplish
            url: Optional starting URL (if provided, agent navigates there first)
            state_name: Optional name of saved state to load (e.g., 'admin_session')
            save_state_as: Optional name to save state as after task completion
            scope: Optional scope constraints for the browser agent
            max_steps: Maximum steps for the browser agent (default: 10)
            purpose: Why this browser task is being executed
            **kwargs: Additional arguments (ignored)
            
        Returns:
            ToolResult with the browser agent's findings
        """
        import uuid
        from tempo.agents.browser import BrowserAgent
        from tempo.agent.config import AgentConfig
        from tempo.agent.runner import Agent
        from tempo.context.store import ContextStore
        from tempo.prompts.builder import PromptBuilder
        
        # Coerce max_steps to int (LLM may pass as string)
        max_steps = int(max_steps)
        
        # Create browser agent definition with new parameters
        browser_agent_def = BrowserAgent(
            task=task,
            url=url if url else None,
            state_name=state_name if state_name else None,
            save_state_as=save_state_as if save_state_as else None,
            scope=scope if scope else None,
            headless=self._headless,
        )
        
        # Create isolated context for browser agent
        browser_context = ContextStore()
        
        # Create tools for browser agent
        browser_tools = browser_agent_def.create_tools(
            context=browser_context,
            container=self._container_manager,
        )
        
        # Always create LLM client with browser agent's model for consistency
        from tempo.infra.llm import LiteLLMClient
        llm = LiteLLMClient(model=browser_agent_def.model)
        
        # Create browser agent config
        config = AgentConfig(
            model=browser_agent_def.model,
            max_total_steps=max_steps,
            browser_headless=self._headless,
        )
        
        # Build prompts
        prompts = PromptBuilder()
        tool_schemas = browser_tools.get_schemas()
        system_prompt = browser_agent_def.build_system_prompt(
            prompts=prompts,
            tool_schemas=tool_schemas,
            scope_description=scope if scope else "Browser automation task",
        )
        
        # Add system prompt to context
        from tempo.context.frame import MessageRole
        browser_context.add_message(MessageRole.SYSTEM, system_prompt)
        
        # Create child visualization collector for browser agent if available
        browser_collector = None
        if self._visualization_collector:
            browser_id = f"browser_{uuid.uuid4().hex[:8]}"
            # Use for_subagent if available (VisualizationCollector)
            if hasattr(self._visualization_collector, "for_subagent"):
                browser_collector = self._visualization_collector.for_subagent(browser_id)
            
            # Emit browser agent start event
            if hasattr(self._visualization_collector, "on_subagent_start"):
                self._visualization_collector.on_subagent_start(
                    subagent_id=browser_id,
                    subagent_type="browser",
                    objective=task,
                )
        
        # Create and run browser agent with visualization
        browser_agent = Agent(
            config=config,
            llm=llm,
            tools=browser_tools,
            context=browser_context,
            visualization_collector=browser_collector,
        )
        
        # Build objective
        objective = browser_agent_def.build_objective()
        
        try:
            # Run browser agent
            result = await browser_agent.run(
                objective=objective,
                max_steps=max_steps,
            )
            
            # Extract findings from result
            if result.success:
                findings = result.findings
                if findings:
                    findings_str = findings[0].get("findings", str(findings))
                    extracted_data = findings[0].get("extracted_data", "")
                    task_success = findings[0].get("success", True)
                else:
                    findings_str = "Browser task completed (no specific findings)"
                    extracted_data = ""
                    task_success = True
                
                output_parts = [f"Browser task completed in {result.steps_taken} steps."]
                output_parts.append(f"\nFindings: {findings_str}")
                if extracted_data:
                    output_parts.append(f"\nExtracted data: {extracted_data}")
                
                # Emit subagent finish event
                if self._visualization_collector and hasattr(self._visualization_collector, "on_subagent_finish"):
                    self._visualization_collector.on_subagent_finish(
                        subagent_id=browser_id if "browser_id" in dir() else "browser",
                        success=task_success,
                        summary=findings_str[:200],
                        findings_count=1 if findings else 0,
                        surfaces_count=0,
                    )
                
                return ToolResult(
                    success=task_success,
                    output="\n".join(output_parts),
                    metadata={
                        "steps_taken": result.steps_taken,
                        "findings": findings_str,
                        "extracted_data": extracted_data,
                        "state_loaded": state_name if state_name else None,
                        "state_saved": save_state_as if save_state_as else None,
                    },
                )
            else:
                # Emit subagent finish event for failure
                if self._visualization_collector and hasattr(self._visualization_collector, "on_subagent_finish"):
                    self._visualization_collector.on_subagent_finish(
                        subagent_id=browser_id if "browser_id" in dir() else "browser",
                        success=False,
                        summary=result.error or "Unknown error",
                        findings_count=0,
                        surfaces_count=0,
                    )
                
                return ToolResult(
                    success=False,
                    output=f"Browser task failed: {result.error or 'Unknown error'}",
                    error=result.error,
                    metadata={"steps_taken": result.steps_taken},
                )
                
        except Exception as e:
            return ToolResult(
                success=False,
                output=f"Error running browser agent: {str(e)}",
                error=str(e),
            )
    
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
                    "max_steps": {
                        "type": "integer",
                        "description": "Maximum steps for the browser agent (default: 10)",
                        "default": 10,
                    },
                },
                "required": ["task"],
            },
        )
