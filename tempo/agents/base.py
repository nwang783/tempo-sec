"""
Base class for agent definitions.

Provides common functionality for agent definitions and ensures
they conform to the AgentDefinition protocol.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tempo.context.store import ContextStore
    from tempo.infra.container import ContainerManager
    from tempo.tools.registry import ToolRegistry
    from tempo.prompts.builder import PromptBuilder


class BaseAgentDefinition(ABC):
    """
    Base class for agent definitions.
    
    Provides default implementations and enforces the interface
    required by the AgentDefinition protocol.
    
    Subclasses must implement:
    - name (property)
    - description (property)
    - create_tools()
    - build_objective()
    
    Optional overrides:
    - model (default: claude-sonnet-4)
    - build_system_prompt() (default: uses PromptBuilder.build_full_prompt)
    """
    
    # Default model - subclasses can override
    _model: str = "anthropic/claude-sonnet-4-20250514"
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this agent (e.g., 'recon', 'test_cycle')."""
        ...
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what this agent does."""
        ...
    
    @property
    def model(self) -> str:
        """LLM model to use."""
        return self._model
    
    @abstractmethod
    def create_tools(
        self,
        context: "ContextStore",
        container: "ContainerManager | None" = None,
        **kwargs: Any,
    ) -> "ToolRegistry":
        """
        Create the tool registry for this agent.
        
        Args:
            context: ContextStore instance
            container: Optional ContainerManager for sandboxed execution
            **kwargs: Additional agent-specific parameters
            
        Returns:
            ToolRegistry with tools for this agent
        """
        ...
    
    def build_system_prompt(
        self,
        prompts: "PromptBuilder",
        tool_schemas: list[dict],
        scope_description: str,
    ) -> str:
        """
        Build the system prompt for this agent.
        
        Default implementation uses PromptBuilder.build_full_prompt().
        Subclasses can override for custom prompts.
        
        Args:
            prompts: PromptBuilder instance
            tool_schemas: List of tool schemas in OpenAI format
            scope_description: Scope/limits for testing
            
        Returns:
            Formatted system prompt string
        """
        return prompts.build_full_prompt(
            tool_schemas=tool_schemas,
            scope_description=scope_description,
        )
    
    @abstractmethod
    def build_objective(self, target: str | None = None, **kwargs: Any) -> str:
        """
        Build the user objective from runtime parameters.
        
        Args:
            target: Primary target (URL, path, etc.), optional for sub-agents
            **kwargs: Additional agent-specific parameters
            
        Returns:
            Formatted objective string
        """
        ...
