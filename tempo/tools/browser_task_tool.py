"""
Browser Task Tool.

Tool for parent agents to delegate browser tasks to a specialized browser agent.
"""

from typing import TYPE_CHECKING

from tempo.tools.base import Tool, ToolCategory, ToolResult, ToolSchema

if TYPE_CHECKING:
    from tempo.infra.container import ContainerManager
    from tempo.infra.llm import LLMClient


class BrowserTaskTool(Tool):
    """
    Delegate a browser task to a specialized browser agent.
    
    This tool allows parent agents (Recon, TestCycle) to offload
    browser-based tasks to a dedicated browser agent that runs
    autonomously and returns findings.
    """
    
    name = "browser_task"
    description = (
        "Execute a browser-based task using a specialized browser agent. "
        "Use this for web browsing, form filling, clicking, and page analysis. "
        "The browser agent will complete the task and return its findings."
    )
    category = ToolCategory.BROWSING
    
    def __init__(
        self,
        container_manager: "ContainerManager | None" = None,
        llm_client: "LLMClient | None" = None,
    ):
        """
        Initialize the browser task tool.
        
        Args:
            container_manager: Container for sandboxed browser execution
            llm_client: LLM client for the browser agent (if None, creates new one)
        """
        self._container_manager = container_manager
        self._llm_client = llm_client
    
    async def execute(
        self,
        task: str,
        url: str = "",
        max_steps: int = 10,
    ) -> ToolResult:
        """
        Execute a browser task via the browser agent.
        
        Args:
            task: Description of what the browser agent should accomplish
            url: Optional starting URL (if provided, agent navigates there first)
            max_steps: Maximum steps for the browser agent (default: 10)
            purpose: Why this browser task is being performed
            
        Returns:
            ToolResult with the browser agent's findings
        """
        from tempo.agents.browser import BrowserAgent
        from tempo.agent.config import AgentConfig
        from tempo.agent.runner import Agent
        from tempo.context.store import ContextStore
        from tempo.prompts.builder import PromptBuilder
        
        # Create browser agent definition
        browser_agent_def = BrowserAgent(
            task=task,
            url=url if url else None,
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
            max_steps=max_steps,
        )
        
        # Build prompts
        prompts = PromptBuilder()
        tool_schemas = browser_tools.get_schemas()
        system_prompt = browser_agent_def.build_system_prompt(
            prompts=prompts,
            tool_schemas=tool_schemas,
            scope_description="Browser automation task",
        )
        
        # Create and run browser agent
        browser_agent = Agent(
            config=config,
            llm=llm,
            tools=browser_tools,
            context=browser_context,
            system_prompt=system_prompt,
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
                
                return ToolResult(
                    success=task_success,
                    output="\n".join(output_parts),
                    metadata={
                        "steps_taken": result.steps_taken,
                        "findings": findings_str,
                        "extracted_data": extracted_data,
                    },
                )
            else:
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
                    "max_steps": {
                        "type": "integer",
                        "description": "Maximum steps for the browser agent (default: 10)",
                        "default": 10,
                    },
                },
                "required": ["task"],
            },
        )
