"""
Recon Agent Definition.

Agent for performing reconnaissance on a target and producing a structured manifest.
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
class ReconAgent(BaseAgentDefinition):
    """
    Reconnaissance agent that produces target manifests.
    
    Performs comprehensive reconnaissance on a target domain:
    - Crawls endpoints and pages
    - Fingerprints technologies
    - Identifies attack surfaces
    - Produces a structured manifest file
    """
    
    _name = "recon"
    _model = "openai/gpt-5-mini"
    _initial_phase = Phase.RECON
    
    def __init__(
        self,
        target: str,
        output_path: str | None = None,
        session_id: str | None = None,
        **kwargs: Any,
    ):
        """
        Initialize the recon agent.
        
        Args:
            target: Target domain or URL
            output_path: Path for manifest output (default: auto-generated)
            session_id: Session ID for context persistence
            **kwargs: Ignored additional args
        """
        self.target = target
        self._target_domain = target.replace("https://", "").replace("http://", "").split("/")[0]
        self._output_path = output_path
        self._session_id = session_id or ""
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def description(self) -> str:
        return "Reconnaissance agent that produces target manifests"
    
    @property
    def output_path(self) -> str:
        """Get or compute the output path for the manifest."""
        if self._output_path:
            return self._output_path
        return f"./manifests/{self._target_domain.replace('.', '_')}_manifest.json"
    
    def create_tools(
        self,
        context: "ContextStore",
        container: "ContainerManager | None" = None,
        workflow: "WorkflowManager | None" = None,
        **kwargs: Any,
    ) -> "ToolRegistry":
        """Create recon-specific tools."""
        from tempo.tools.registry import ToolRegistry
        from tempo.tools.shell import ShellTool
        from tempo.tools.filesystem import FileReadTool, FileWriteTool
        from tempo.tools.browser_tools import (
            BrowserSession,
            BrowserNavigateTool,
            BrowserSnapshotTool,
            BrowserClickTool,
            BrowserTypeTool,
            BrowserFillFormTool,
        )
        from tempo.tools.meta import SummarizeOutputTool
        from tempo.tools.manifest_tools import CompleteReconTool
        from tempo.tools.view_output import ViewToolOutputTool
        
        tools = ToolRegistry()
        
        # Core tools
        tools.register(ShellTool(container_manager=container))
        tools.register(FileReadTool(container_manager=container))
        tools.register(FileWriteTool(container_manager=container))
        
        # Browser tools
        browser_session = BrowserSession(container_manager=container)
        tools.register(BrowserNavigateTool(browser_session))
        tools.register(BrowserSnapshotTool(browser_session))
        tools.register(BrowserClickTool(browser_session))
        tools.register(BrowserTypeTool(browser_session))
        tools.register(BrowserFillFormTool(browser_session))
        
        # Meta tools
        tools.register(SummarizeOutputTool(context_store=context))
        tools.register(ViewToolOutputTool(context_store=context))
        
        # Recon completion tool
        tools.register(CompleteReconTool(
            output_path=self.output_path,
            target_domain=self._target_domain,
            agent_model=self.model,
            session_id=self._session_id,
            context_store=context,
        ))
        
        return tools
    
    def build_system_prompt(
        self,
        prompts: "PromptBuilder",
        tool_schemas: list[dict],
        scope_description: str,
    ) -> str:
        """Build recon-specific system prompt (no phase transitions)."""
        return prompts.build_recon_prompt(
            objective=f"Perform comprehensive reconnaissance on {self.target}",
            tool_schemas=tool_schemas,
            scope_description=scope_description,
        )
    
    def build_objective(self, target: str | None = None, **kwargs: Any) -> str:
        """Build the recon objective."""
        target = target or self.target
        return f"""Target: {target}

Tasks:
1. Crawl the website to discover endpoints and pages
2. Fingerprint technologies (web server, frameworks, libraries)
3. Identify forms, APIs, and input points
4. Note authentication mechanisms
5. Look for misconfigurations or exposed resources

When you have gathered sufficient information, call `complete_recon` to save the manifest."""
