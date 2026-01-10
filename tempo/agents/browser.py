"""
Browser Agent Definition.

A specialized agent for browser automation tasks that can be invoked
by parent agents to handle web interaction subtasks.
"""

from typing import TYPE_CHECKING, Any

from tempo.agents.base import BaseAgentDefinition
from tempo.agents import register_agent
from tempo.prompts.phases import Phase
from tempo.infra.protocols import DEFAULT_SCOPE_PLACEHOLDERS

if TYPE_CHECKING:
    from tempo.context.store import ContextStore
    from tempo.infra.container import ContainerManager
    from tempo.infra.browser_state import BrowserStateManager
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
    - State management tools (save, load, list, delete states)
    - Visual tools (screenshot, coordinate click, scroll, wait)
    - Task completion tool to signal done and return findings
    - Scope support for constrained browsing
    - Focused, single-purpose prompt (no phase transitions)
    - Fast model for quick browser tasks
    """
    
    _name = "browser"
    _model = "openai/gpt-5.1"  # Vision-capable model for visual browsing
    _initial_phase = Phase.RECON  # Single phase, no transitions
    
    def __init__(
        self,
        task: str,
        url: str | None = None,
        state_name: str | None = None,
        save_state_as: str | None = None,
        scope: str | None = None,
        headless: bool = True,
        state_ttl_days: int = 7,
        **kwargs: Any,
    ):
        """
        Initialize the browser agent.
        
        Args:
            task: Description of the browser task to accomplish
            url: Optional starting URL to navigate to
            state_name: Optional name of saved state to load at start
            save_state_as: Optional name to save state as after completion
            scope: Optional scope constraints for the browser agent
            headless: Whether to run browser in headless mode
            state_ttl_days: Default TTL for saved states in days
            **kwargs: Ignored additional args
        """
        self.task = task
        self.url = url
        self.state_name = state_name
        self.save_state_as = save_state_as
        self.scope = scope
        self.headless = headless
        self.state_ttl_days = state_ttl_days
    
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
        state_manager: "BrowserStateManager | None" = None,
        **kwargs: Any,
    ) -> "ToolRegistry":
        """
        Create browser-only tools.
        
        The browser agent has:
        - Browser navigation and interaction tools
        - State management tools (save/load sessions)
        - Visual tools (screenshot, coordinate click/type, scroll, wait)
        - Task completion tool (no other meta tools)
        """
        from tempo.tools.registry import ToolRegistry
        from tempo.tools.browser_tools import (
            BrowserSession,
            BrowserNavigateTool,
            BrowserScreenshotTool,
            BrowserClickCoordsTool,
            BrowserTypeCoordsTool,
            BrowserScrollTool,
            BrowserWaitTool,
            BrowserConsoleTool,
            BrowserNetworkTool,
            BrowserEvaluateTool,
        )
        from tempo.tools.browser_state_tools import (
            BrowserListStatesTool,
            BrowserSaveStateTool,
            BrowserLoadStateTool,
            BrowserDeleteStateTool,
            BrowserCleanupStatesTool,
        )
        from tempo.tools.complete_browser_task import CompleteBrowserTaskTool
        from tempo.tools.meta import SummarizePreviousOutputTool
        from tempo.infra.browser_state import BrowserStateManager
        
        tools = ToolRegistry()
        
        # Create state manager if not provided
        if state_manager is None:
            state_manager = BrowserStateManager(ttl_days=self.state_ttl_days)
        
        # Browser tools with shared session
        browser_session = BrowserSession(
            container_manager=container,
            headless=self.headless,
            state_manager=state_manager,
        )
        
        # Core visual browser tools (no DOM-based tools)
        tools.register(BrowserNavigateTool(browser_session))
        tools.register(BrowserScreenshotTool(browser_session))
        tools.register(BrowserClickCoordsTool(browser_session))
        tools.register(BrowserTypeCoordsTool(browser_session))
        tools.register(BrowserScrollTool(browser_session))
        tools.register(BrowserWaitTool(browser_session))
        
        # Debugging tools
        tools.register(BrowserConsoleTool(browser_session))
        tools.register(BrowserNetworkTool(browser_session))
        tools.register(BrowserEvaluateTool(browser_session))
        
        # State management tools
        tools.register(BrowserListStatesTool(state_manager))
        tools.register(BrowserSaveStateTool(browser_session, state_manager))
        tools.register(BrowserLoadStateTool(browser_session, state_manager))
        tools.register(BrowserDeleteStateTool(state_manager))
        tools.register(BrowserCleanupStatesTool(state_manager))
        
        # Summarization tool (required for large outputs)
        tools.register(SummarizePreviousOutputTool(context))
        
        # Completion tool
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
        Includes scope constraints if provided.
        """
        # Pass scope if it's not a placeholder value
        scope_content = None
        if scope_description and scope_description not in DEFAULT_SCOPE_PLACEHOLDERS:
            scope_content = scope_description
        
        # Also check self.scope which may be passed directly
        if self.scope and not scope_content:
            scope_content = self.scope
        
        return prompts.build_browser_prompt(
            tool_schemas=tool_schemas,
            scope_content=scope_content,
            state_name=self.state_name,
            save_state_as=self.save_state_as,
            ttl_days=self.state_ttl_days,
        )
    
    def build_objective(self, target: str | None = None, **kwargs: Any) -> str:
        """
        Build the browser task objective.
        
        Args:
            target: Ignored (uses url from init)
            **kwargs: Ignored
            
        Returns:
            Formatted objective with task, URL, and state instructions
        """
        objective_parts = [f"**Task**: {self.task}"]
        
        if self.url:
            objective_parts.append(f"\n**Starting URL**: {self.url}")
        else:
            objective_parts.append("\n**Starting URL**: Navigate as needed to accomplish the task")
        
        # Add state loading instruction if specified
        if self.state_name:
            objective_parts.append(
                f"\n**Initial State**: Load saved state '{self.state_name}' "
                "at the start using `browser_load_state`."
            )
        
        # Add state saving instruction if specified
        if self.save_state_as:
            objective_parts.append(
                f"\n**Save State**: Before completing, save browser state as "
                f"'{self.save_state_as}' using `browser_save_state`."
            )
        
        objective_parts.append("\nComplete the task and call `complete_browser_task` with your findings.")
        
        return "\n".join(objective_parts)
