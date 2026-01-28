"""
Dispatch Browser Tool.

Tool for agents to dispatch the specialized browser subagent.
"""

import os
import uuid
from typing import TYPE_CHECKING, Any

from tempo.tools.base import Tool, ToolCategory, ToolResult, ToolSchema
from tempo.infra.browser_session import BrowserSessionManager

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
        keep_alive: bool = False,
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
        
        # Get email credentials from env for email verification flows
        agent_email = os.getenv("TEMPO_AGENT_EMAIL")
        imap_host = os.getenv("TEMPO_IMAP_HOST", "imap.gmail.com")
        imap_password = os.getenv("TEMPO_IMAP_PASSWORD")
        
        # Notify visualization
        if self._visualization and hasattr(self._visualization, 'on_subagent_start'):
            self._visualization.on_subagent_start(
                subagent_id=subagent_id,
                subagent_type="browser_subagent",
                objective=objective,
                parent_id="orchestrator", # Or handle properly if we can get parent ID
            )
        
        # Get shared browser session manager
        session_mgr = BrowserSessionManager.get_instance()
        
        # Configure headless from config if available
        headless = False
        if self._config and hasattr(self._config, 'browser_headless'):
            headless = self._config.browser_headless
        session_mgr.configure(headless=headless)
        
        # Get or create shared browser client
        mcp_client = await session_mgr.get_or_create_client()
        
        # Get session context from previous dispatches
        session_context = session_mgr.get_session_context()
            
        # Initialize Subagent Definition with shared client
        subagent_def = BrowserSubagent(
            objective=objective,
            starting_url=url,
            agent_email=agent_email,
            mcp_client=mcp_client,  # Reuse shared client
            session_context=session_context,  # Previous session history
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
            agent_email=agent_email,
            imap_host=imap_host,
            imap_password=imap_password,
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

            # Extract summary from findings
            summary = "Browser Subagent Completed"
            browser_state = None
            if result.findings:
                last_finding = result.findings[-1]
                summary = last_finding.get("findings", summary)
                browser_state = last_finding.get("browser_state")
            elif result.error:
                summary = f"Error: {result.error}"

            # Visualization Finish
            if self._visualization and hasattr(self._visualization, 'on_subagent_finish'):
                self._visualization.on_subagent_finish(
                    subagent_id=subagent_id,
                    success=result.success,
                    summary=summary,
                    findings_count=0,
                    surfaces_count=0,
                )

            metadata = {
                "subagent_id": subagent_id,
                "steps": result.steps_taken
            }
            
            # Format session state for AI visibility
            session_info = ""
            if browser_state:
                metadata["browser_state"] = browser_state
                session_info = self._format_session_state(browser_state)
                # Note: Cannot store mcp_client in metadata (asyncio objects aren't serializable)
                # For keep_alive, the browser stays open but client reuse requires different approach

            return ToolResult(
                success=result.success,
                output=f"Browser Subagent Completed:\n{summary}\n\n{session_info}",
                metadata=metadata
            )

        except Exception as e:
            if self._visualization and hasattr(self._visualization, 'on_subagent_finish'):
                self._visualization.on_subagent_finish(
                    subagent_id=subagent_id,
                    success=False,
                    summary=str(e),
                    findings_count=0,
                    surfaces_count=0,
                )
            return ToolResult(success=False, output=str(e), error=str(e))
        finally:
            # Store session summary for future dispatches (even on error)
            try:
                final_summary = summary if 'summary' in dir() else "Session ended"
                session_mgr.add_session_summary(
                    objective=objective,
                    summary=final_summary,
                    browser_state=browser_state if 'browser_state' in dir() else None,
                )
            except Exception:
                pass  # Don't fail dispatch on history error
            
            # NOTE: We no longer stop the server here - it's managed by BrowserSessionManager

    def _format_session_state(self, state: dict) -> str:
        """Format browser state for AI visibility with actual values."""
        lines = ["## Session State Captured"]
        
        # URL
        if state.get("url"):
            lines.append(f"- **Current URL**: {state['url']}")
        
        # Cookies (show full details)
        cookies = state.get("cookies", [])
        if cookies:
            lines.append(f"\n### Cookies ({len(cookies)})")
            for c in cookies[:15]:  # Limit to 15 for readability
                # Handle both dict format and string format
                if isinstance(c, dict):
                    name = c.get("name", "?")
                    value = c.get("value", "")
                else:
                    # Simple string representation
                    name = str(c)
                    value = ""
                # Truncate very long values
                if len(value) > 100:
                    value = value[:100] + "..."
                if value:
                    lines.append(f"- `{name}`: `{value}`")
                else:
                    lines.append(f"- `{name}`")
            if len(cookies) > 15:
                lines.append(f"- *(and {len(cookies) - 15} more)*")
        
        # Local Storage (show full key-values)
        ls = state.get("local_storage", {})
        if ls:
            lines.append(f"\n### LocalStorage ({len(ls)} keys)")
            for i, (key, value) in enumerate(list(ls.items())[:10]):
                # Truncate long values
                display_value = str(value)
                if len(display_value) > 100:
                    display_value = display_value[:100] + "..."
                lines.append(f"- `{key}`: `{display_value}`")
            if len(ls) > 10:
                lines.append(f"- *(and {len(ls) - 10} more)*")
        
        # Session Storage
        ss = state.get("session_storage", {})
        if ss:
            lines.append(f"\n### SessionStorage ({len(ss)} keys)")
            for i, (key, value) in enumerate(list(ss.items())[:10]):
                display_value = str(value)
                if len(display_value) > 100:
                    display_value = display_value[:100] + "..."
                lines.append(f"- `{key}`: `{display_value}`")
            if len(ss) > 10:
                lines.append(f"- *(and {len(ss) - 10} more)*")
        
        lines.append("\n*Full state available in `metadata.browser_state`*")
        return "\n".join(lines)

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
                    "keep_alive": {
                        "type": "boolean",
                        "description": "Keep browser session alive after completion for authenticated testing reuse. Returns client handle in metadata.",
                        "default": False,
                    },
                },
                "required": ["objective"],
            },
        )
