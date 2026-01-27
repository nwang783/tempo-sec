"""
Browser Subagent Definition.

A specialized subagent for performing browser automation tasks using Playwright MCP tools.
"""

from typing import TYPE_CHECKING, Any

from tempo.agents.base import BaseAgentDefinition
from tempo.agents import register_agent
from tempo.tools.base import Tool, ToolResult, ToolSchema

if TYPE_CHECKING:
    from tempo.context.store import ContextStore
    from tempo.infra.container import ContainerManager
    from tempo.tools.registry import ToolRegistry
    from tempo.prompts.builder import PromptBuilder


class PlaywrightToolWrapper(Tool):
    """
    Wrapper for Playwright MCP tools to start/stop the server lazily if needed,
    or assume the server is managed by the Dispatch tool or shared client.
    
    However, since we want the subagent to use the tools directly, and the `HeadlessBrowserTool`
    previously managed the client, we need a way to share the client or manage it.
    
    For the BrowserSubagent, we will instantiate a *single* PlaywrightMCPClient that persists
    for the lifecycle of the agent (or is passed in).
    
    Actually, simpler: we'll create a single `PlaywrightMCPClient` in `create_tools` and 
    register wrappers that call it.
    """
    
    def __init__(
        self,
        name: str,
        description: str,
        tool_func: Any,
        schema: dict,
        output_store: "Any" = None,
        summary_chars: int = 2000,
    ):
        self._name = name
        self._description = description
        self._tool_func = tool_func
        self._schema_dict = schema
        self._output_store = output_store
        self._summary_chars = summary_chars
        
    @property
    def name(self) -> str:
        return self._name
        
    @property
    def description(self) -> str:
        return self._description
        
    async def execute(self, **kwargs) -> ToolResult:
        # Filter out 'purpose' if it's there but not expected by the underlying tool
        # (Though we might want to log it)
        if "purpose" in kwargs:
            kwargs.pop("purpose")

        # Normalize browser_evaluate inputs to MCP expected shape.
        # MCP expects "function" but callers often send "script".
        if self._name == "browser_evaluate" and "function" not in kwargs and "script" in kwargs:
            kwargs["function"] = kwargs.pop("script")

        # Normalize element/ref inputs for element-based tools.
        if self._name in ("browser_click", "browser_hover", "browser_select_option", "browser_file_upload"):
            element_val = kwargs.get("element") or kwargs.get("ref")
            if isinstance(element_val, dict):
                element_val = element_val.get("ref")
            if isinstance(element_val, str):
                if element_val.startswith("ref="):
                    element_val = element_val.split("=", 1)[1]
                kwargs["ref"] = element_val
                kwargs.pop("element", None)

        # Normalize drag source/target refs.
        if self._name == "browser_drag":
            for key in ("source", "target"):
                val = kwargs.get(key)
                if isinstance(val, dict):
                    val = val.get("ref")
                if isinstance(val, str) and val.startswith("ref="):
                    kwargs[key] = val.split("=", 1)[1]
            
        result = await self._tool_func(self._name, kwargs)
        
        success = result.get("success", False)
        output = result.get("output", "")
        error = result.get("error")
        
        stored_handle = None
        stored_chars = 0
        stored_notice = ""
        stored_output = output
        if not stored_output and result.get("raw_result") is not None:
            import json
            stored_output = json.dumps(result.get("raw_result"), ensure_ascii=True)

        if self._output_store is not None:
            try:
                stored_handle = self._output_store.save(
                    stored_output or "",
                    metadata={
                        "tool": self._name,
                        "success": success,
                        "error": str(error) if error else "",
                    },
                )
                stored_chars = len(stored_output or "")
                stored_notice = f"[Stored output: {stored_handle} | {stored_chars} chars]"
            except Exception:
                stored_handle = None

        summarized_output = output
        if self._summary_chars and output:
            summarized_output = output[: self._summary_chars]
            if len(output) > self._summary_chars:
                summarized_output += f"\n[Output truncated to {self._summary_chars} chars]"

        if stored_notice:
            summarized_output = f"{stored_notice}\n{summarized_output}"

        if not success and error:
            return ToolResult(
                success=False,
                output=summarized_output or str(error),
                error=str(error),
                metadata={
                    "output_handle": stored_handle,
                    "output_chars": stored_chars,
                },
            )
            
        return ToolResult(
            success=True, 
            output=summarized_output,
            structured_data=None if stored_handle else result.get("raw_result"),
            metadata={
                "output_handle": stored_handle,
                "output_chars": stored_chars,
            },
        )

    def get_schema(self) -> ToolSchema:
        # Convert schema dict to ToolSchema
        # We need to sanitize properties to remove the custom "required" boolean field
        # which is not valid JSON Schema (required should only be a top-level array).
        raw_params = self._schema_dict.get("parameters", {})
        properties = {}
        required_fields = []
        
        for name, defn in raw_params.items():
            # Create a copy to avoid modifying the original
            prop_def = defn.copy()
            
            # Check for required flag and add to list if present
            if prop_def.pop("required", False):
                required_fields.append(name)
                
            properties[name] = prop_def
            
        return ToolSchema(
            name=self._name,
            description=self._description,
            parameters={
                "type": "object",
                "properties": properties,
                "required": required_fields,
            },
        )


@register_agent
class BrowserSubagent(BaseAgentDefinition):
    """
    Browser automation subagent.
    
    Uses Playwright MCP tools directly to navigate and interact with web pages.
    Designed to be called by other agents (Recon, Test) for specific browser tasks.
    """
    
    _name = "browser_subagent"
    _model = "openai/gpt-5-mini"  # Fast, efficient model
    
    def __init__(
        self,
        objective: str,
        starting_url: str = "",
        session_id: str = "",
        **kwargs: Any,
    ):
        self.objective = objective
        self.starting_url = starting_url
        self.session_id = session_id
        
        # We will hold the client reference to ensure it's closed
        self._client = None
        
    @property
    def name(self) -> str:
        return self._name
        
    @property
    def description(self) -> str:
        return "Browser automation subagent using Playwright MCP"
        
    def create_tools(
        self,
        context: "ContextStore",
        container: "ContainerManager | None" = None,
        **kwargs: Any,
    ) -> "ToolRegistry":
        from tempo.tools.registry import ToolRegistry
        from tempo.infra.playwright_mcp import PlaywrightMCPClient, PLAYWRIGHT_MCP_TOOLS
        from tempo.tools.complete_browser_task import CompleteBrowserTaskTool
        from tempo.tools.meta import SummarizePreviousOutputTool
        from tempo.infra.output_store import OutputStore
        from tempo.tools.output_store_tools import (
            SearchStoredOutputTool,
            GetStoredOutputRangeTool,
        )
        
        tools = ToolRegistry()
        
        # Initialize client (headless by default, or config/kwargs)
        # We'll start it lazily or here? 
        # Better to start it when first tool is called, or ideally the agent runner context manages start/stop?
        # For now, we'll let the wrappers trigger start if needed, but we need a shared client instance.
        
        self._client = PlaywrightMCPClient(headless=True)
        # We should start it immediately or lazily. 
        # Since tools are synchronous creation but async execution, we can't await start_server here.
        output_store = OutputStore.default()
        
        async def call_mcp_tool(name: str, params: dict) -> dict:
            if not self._client._server_ready:
                await self._client.start_server()
            return await self._client.call_tool(name, params)
            
        # Register all Playwright MCP tools
        for tool_name, tool_def in PLAYWRIGHT_MCP_TOOLS.items():
            tool = PlaywrightToolWrapper(
                name=tool_name,
                description=tool_def["description"],
                tool_func=call_mcp_tool,
                schema=tool_def,
                output_store=output_store,
            )
            tools.register(tool)
            
        # Register completion tool
        tools.register(CompleteBrowserTaskTool())
        
        # Register summarization tool
        tools.register(SummarizePreviousOutputTool(context_store=context))

        # Register stored output tools
        tools.register(SearchStoredOutputTool(output_store))
        tools.register(GetStoredOutputRangeTool(output_store))
        
        return tools
        
    def build_system_prompt(
        self,
        prompts: "PromptBuilder",
        tool_schemas: list[dict],
        scope_description: str = "",
    ) -> str:
        """
        Build the browser subagent system prompt.
        """
        return prompts.build_browser_subagent_prompt(
            tool_schemas=tool_schemas,
            objective=self.objective,
            starting_url=self.starting_url,
            scope_content=scope_description,
        )

    def build_objective(self, target: str | None = None, **kwargs: Any) -> str:
        return self.objective
