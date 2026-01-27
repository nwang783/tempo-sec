"""
Dispatch Browser Tool.

Tool for agents to dispatch the specialized browser subagent.
"""

import uuid
from typing import TYPE_CHECKING, Any

from tempo.tools.base import Tool, ToolCategory, ToolResult, ToolSchema

if TYPE_CHECKING:
    from tempo.infra.container import ContainerManager
    from tempo.infra.protocols import VisualizationObserver, FindingsUpdater


class DispatchBrowserTool(Tool):
    """
    Dispatch the browser subagent to perform a specific browsing task.
    
    This tool spawns a BrowserSubagent which has direct access to Playwright tools.
    """
    
    name = "dispatch_browser"
    description = (
        "Dispatch a specialized browser subagent to perform a browsing task. "
        "Use this for any task requiring navigation, clicking, typing, or web inspection. "
        "The subagent will perform the actions and return the result."
    )
    category = ToolCategory.META
    
    def __init__(
        self,
        container_manager: "ContainerManager | None" = None,
        visualization: "VisualizationObserver | None" = None,
        config: "Any" = None,
    ):
        self._container_manager = container_manager
        self._visualization = visualization
        self._config = config
        
    async def execute(
        self,
        objective: str,
        url: str = "",
        scope: str = "",
        purpose: str = "",
        **kwargs,
    ) -> ToolResult:
        """
        Execute the browser subagent.
        
        Args:
            objective: What the subagent should accomplish
            url: Optional starting URL
            purpose: Why this dispatch is being made
            kwargs: Additional args
            
        Returns:
            ToolResult containing the subagent's output
        """
        from tempo.agents.browser_subagent import BrowserSubagent
        from tempo.agent.runner import Agent
        from tempo.context.store import ContextStore
        from tempo.context.frame import MessageRole
        from tempo.prompts.builder import PromptBuilder
        from tempo.infra.llm import LiteLLMClient
        from tempo.agent.config import AgentConfig
        
        # unique ID
        subagent_id = str(uuid.uuid4())[:8]
        
        # Notify visualization
        if self._visualization and hasattr(self._visualization, 'on_subagent_start'):
            self._visualization.on_subagent_start(
                subagent_id=subagent_id,
                subagent_type="browser_subagent",
                objective=objective,
                parent_id="orchestrator", # Or handle properly if we can get parent ID
            )
            
        # Initialize Subagent Definition
        subagent_def = BrowserSubagent(
            objective=objective,
            starting_url=url,
        )
        
        # Context
        subagent_context = ContextStore()
        
        # Vis for subagent
        subagent_viz = None
        if self._visualization and hasattr(self._visualization, 'for_subagent'):
            subagent_viz = self._visualization.for_subagent(subagent_id)
            
        # Tools
        subagent_tools = subagent_def.create_tools(
            context=subagent_context,
            container=self._container_manager,
            visualization=subagent_viz,
            config=self._config,
        )
        
        # LLM
        model = getattr(subagent_def, "_model", "openai/gpt-5-mini")
        llm = LiteLLMClient(model=model)
        
        # Config
        config = self._config if self._config else AgentConfig(model=model)
        
        # Prompts (using generic builder)
        prompts = PromptBuilder()
        tool_schemas = subagent_tools.get_schemas()
        
        # Using the custom build_system_prompt from BrowserSubagent which essentially returns raw string
        # We might need to ensure schemas are included if the prompt method didn't include them.
        # Our implementation of BrowserSubagent.build_system_prompt handles basic text, 
        # but usually the runner or PromptBuilder injects tool schemas.
        # Let's trust the runner/LLM to handle schemas if passed to the API.
        # But if we want them in system prompt, we need to add them.
        
        system_prompt = subagent_def.build_system_prompt(
            prompts=prompts,
            tool_schemas=tool_schemas,
            scope_description=scope,
        )
        
        # Add system prompt
        subagent_context.add_message(MessageRole.SYSTEM, system_prompt)
        
        # Register viz
        if subagent_viz and hasattr(self._visualization, 'server'):
            self._visualization.server.register_subagent(
                subagent_id=subagent_id,
                context=subagent_context,
                metadata={"type": "browser", "objective": objective},
            )
            
        # Agent Runner
        agent = Agent(
            config=config,
            llm=llm,
            tools=subagent_tools,
            context=subagent_context,
            visualization_collector=subagent_viz,
        )
        
        try:
            # Run
            result = await agent.run(objective=objective)
            
            # Close client if it was created in create_tools and stored in subagent_def
            if hasattr(subagent_def, "_client") and subagent_def._client:
                await subagent_def._client.stop_server()
                
            # Visualization Finish
                # Extract summary from findings
                summary = "Browser Subagent Completed"
                if result.findings:
                    last_finding = result.findings[-1]
                    summary = last_finding.get("findings", summary)
                elif result.error:
                    summary = f"Error: {result.error}"

                self._visualization.on_subagent_finish(
                    subagent_id=subagent_id,
                    success=result.success,
                    summary=summary,
                    findings_count=0,
                    surfaces_count=0,
                )
                
            return ToolResult(
                success=result.success,
                output=f"Browser Subagent Completed:\n{summary}",
                metadata={
                    "subagent_id": subagent_id,
                    "steps": result.steps_taken
                }
            )
            
        except Exception as e:
            if hasattr(subagent_def, "_client") and subagent_def._client:
                await subagent_def._client.stop_server()
                
            if self._visualization and hasattr(self._visualization, 'on_subagent_finish'):
                self._visualization.on_subagent_finish(
                    subagent_id=subagent_id,
                    success=False,
                    summary=str(e),
                    findings_count=0,
                    surfaces_count=0,
                )
            return ToolResult(success=False, output=str(e), error=str(e))

    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "objective": {
                        "type": "string",
                        "description": "The goal for the browser subagent",
                    },
                    "url": {
                        "type": "string",
                        "description": "Optional starting URL",
                        "default": "",
                    },
                    "scope": {
                        "type": "string",
                        "description": "Optional testing scope (allowed/forbidden domains, etc)",
                        "default": "",
                    },
                    "purpose": {
                        "type": "string",
                        "description": "Why this dispatch is needed",
                        "default": "",
                    },
                },
                "required": ["objective"],
            },
        )
