"""
Browser Agent Definition.

A specialized agent for browser automation tasks that can be invoked
by parent agents to handle web interaction subtasks.
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


@register_agent
class BrowserAgent(BaseAgentDefinition):
    """
    Browser automation agent for web interaction tasks.
    
    This agent is designed to be invoked as a sub-agent by parent agents
    (like Recon or TestCycle) to handle specific browser-based tasks.
    
    Features:
    - Browser-only tools (navigate, snapshot, click, type, fill_form)
    - Task completion tool to signal done and return findings
    - Focused, single-purpose prompt (no phase transitions)
    - Fast model for quick browser tasks
    """
    
    _name = "browser"
    _model = "openai/gpt-5-mini"  # Fast model for browser tasks
    _initial_phase = Phase.RECON  # Single phase, no transitions
    
    def __init__(
        self,
        task: str,
        url: str | None = None,
        **kwargs: Any,
    ):
        """
        Initialize the browser agent.
        
        Args:
            task: Description of the browser task to accomplish
            url: Optional starting URL to navigate to
            **kwargs: Ignored additional args
        """
        self.task = task
        self.url = url
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def description(self) -> str:
        return "Browser automation agent for web interaction tasks"
    
    def create_tools(
        self,
        context: "ContextStore",
        container: "ContainerManager | None" = None,
        workflow: "WorkflowManager | None" = None,
        **kwargs: Any,
    ) -> "ToolRegistry":
        """
        Create browser-only tools.
        
        The browser agent has a minimal toolset:
        - Browser navigation and interaction tools
        - Task completion tool (no other meta tools)
        """
        from tempo.tools.registry import ToolRegistry
        from tempo.tools.browser_tools import (
            BrowserSession,
            BrowserNavigateTool,
            BrowserSnapshotTool,
            BrowserClickTool,
            BrowserTypeTool,
            BrowserFillFormTool,
        )
        from tempo.tools.complete_browser_task import CompleteBrowserTaskTool
        
        tools = ToolRegistry()
        
        # Browser tools with shared session
        browser_session = BrowserSession(container_manager=container)
        tools.register(BrowserNavigateTool(browser_session))
        tools.register(BrowserSnapshotTool(browser_session))
        tools.register(BrowserClickTool(browser_session))
        tools.register(BrowserTypeTool(browser_session))
        tools.register(BrowserFillFormTool(browser_session))
        
        # Completion tool - the only meta tool
        tools.register(CompleteBrowserTaskTool())
        
        return tools
    
    def build_system_prompt(
        self,
        prompts: "PromptBuilder",
        tool_schemas: list[dict],
        scope_description: str,
    ) -> str:
        """
        Build browser-specific system prompt.
        
        Uses a focused prompt without phase transitions or security testing context.
        """
        return prompts.build_browser_prompt(tool_schemas=tool_schemas)
    
    def build_objective(self, target: str | None = None, **kwargs: Any) -> str:
        """
        Build the browser task objective.
        
        Args:
            target: Ignored (uses url from init)
            **kwargs: Ignored
            
        Returns:
            Formatted objective with task and optional URL
        """
        objective_parts = [f"**Task**: {self.task}"]
        
        if self.url:
            objective_parts.append(f"\n**Starting URL**: {self.url}")
        else:
            objective_parts.append("\n**Starting URL**: Navigate as needed to accomplish the task")
        
        objective_parts.append("\nComplete the task and call `complete_browser_task` with your findings.")
        
        return "\n".join(objective_parts)
