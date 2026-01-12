"""
Protocol definitions for cross-component type hints.

These protocols allow tools and other components to type-hint against
interfaces without importing from agent internals, following the
dependency rule:

    Context, Prompts, and Tools MUST NOT import from each other.
    They may only import from infra/ or external packages.

By defining protocols here in infra/, tools can use these for type hints
while the actual implementations remain in agent/ or context/.
"""

from typing import Protocol, Any


# Default scope placeholder values that should not be passed to prompts
DEFAULT_SCOPE_PLACEHOLDERS = frozenset({"Subagent task", "No specific scope constraints."})


class ContextSummarizer(Protocol):
    """Protocol for components that can summarize tool call outputs."""
    
    def summarize_tool_call(self, tool_call_id: str, summary: str) -> None:
        """
        Replace a tool call's output with a summary.
        
        Args:
            tool_call_id: ID of the tool call to summarize
            summary: Concise summary text
        """
        ...


class BranchSpawner(Protocol):
    """Protocol for components that can spawn parallel subtasks."""
    
    async def spawn_subtasks(self, subtasks: list[str]) -> str:
        """
        Spawn subagents for parallel task execution.
        
        Args:
            subtasks: List of subtask objective strings
            
        Returns:
            Branch ID for tracking completion
        """
        ...


class ToolOutputViewer(Protocol):
    """Protocol for viewing tool output ranges."""

    def get_tool_output_range(
        self,
        tool_call_id: str,
        start_char: int,
        end_char: int,
    ) -> str | None:
        """
        Get a specific range of a tool call's output.

        Args:
            tool_call_id: ID of the tool call
            start_char: Starting character position
            end_char: Ending character position

        Returns:
            The requested output range, or None if not found
        """
        ...


class OutputStorage(Protocol):
    """Protocol for storing truncated tool outputs to files."""

    def save_output(
        self,
        tool_call_id: str,
        content: str,
        tool_name: str = "",
    ) -> str | None:
        """
        Save tool output to a file.

        Args:
            tool_call_id: Unique ID of the tool call
            content: Full output content to save
            tool_name: Name of the tool (for metadata)

        Returns:
            File path where content was saved, or None if saving disabled/failed
        """
        ...

    def cleanup_expired(self) -> int:
        """Remove expired output files. Returns count of deleted files."""
        ...


class TestPlanManager(Protocol):
    """Protocol for components that can manage the test plan checklist."""
    
    def add_test_plan_item(
        self,
        description: str,
        priority: str = "medium",
    ) -> str:
        """
        Add a new item to the test plan.
        
        Args:
            description: What to investigate
            priority: high/medium/low
            
        Returns:
            ID of the created item
        """
        ...
    
    def complete_test_plan_item(
        self,
        item_id: str,
        status: str,
        reason: str,
    ) -> bool:
        """
        Mark a test plan item as completed or skipped.
        
        Args:
            item_id: ID of the item
            status: "completed" or "skipped"
            reason: Explanation of findings or why skipped
            
        Returns:
            True if item was found and updated
        """
        ...
    
    def get_test_plan(self) -> list[dict]:
        """Get the current test plan items."""
        ...
    
    def set_test_plan(self, items: list[dict]) -> None:
        """Replace the entire test plan."""
        ...


class ToolCallFinder(Protocol):
    """Protocol for finding tool calls in context history."""
    
    def find_tool_call(self, tool_call_id: str) -> Any | None:
        """
        Find a tool call by ID in the context history.
        
        Args:
            tool_call_id: ID of the tool call to find
            
        Returns:
            The ToolCall if found, None otherwise
        """
        ...


class VisualizationObserver(Protocol):
    """
    Protocol for components that observe agent execution events.
    
    This allows the Agent to notify visualization components without
    depending on concrete implementations, following the project's
    dependency rules.
    """
    
    def on_step(self, step_data: dict, frame_id: str) -> None:
        """
        Called when an agent step completes.
        
        Args:
            step_data: Serialized step result containing:
                - step_number: int
                - phase: str | None (if phase transition occurred)
                - error: str | None
                - should_continue: bool
                - llm_content: str | None
                - usage: dict (token usage stats)
            frame_id: ID of the current context frame
        """
        ...
    
    def on_tool_call(self, tool_data: dict, frame_id: str) -> None:
        """
        Called when a tool execution completes.
        
        Args:
            tool_data: Serialized tool call containing:
                - id: str
                - tool_name: str
                - input: dict
                - raw_output: str
                - summary: str | None
                - success: bool
                - error: str | None
                - duration_ms: int
            frame_id: ID of the current context frame
        """
        ...
    
    def on_agent_start(self, objective: str, model_name: str = "") -> None:
        """
        Called when agent starts execution.
        
        Args:
            objective: The task objective
            model_name: Name of the LLM being used
        """
        ...
    
    def on_agent_finish(self, success: bool, output: Any = None) -> None:
        """
        Called when agent finishes execution.
        
        Args:
            success: Whether the agent completed successfully
            output: Final output/result if any
        """
        ...


class FindingsUpdater(Protocol):
    """
    Protocol for components that can update findings documents.

    This allows tools to interact with the findings document without
    importing from the findings module directly, following the
    dependency rules.
    """

    def add_attack_surface(
        self,
        surface_id: str,
        surface_type: str,
        url: str,
        description: str,
        discovered_by: str,
        parameters: list[str] | None = None,
        technology_hints: list[str] | None = None,
        priority: str = "medium",
    ) -> Any:
        """
        Add a new attack surface to the findings document.

        Args:
            surface_id: Unique identifier (UUID)
            surface_type: Type of surface (endpoint, form, api, etc.)
            url: Full URL or location
            description: Detailed description
            discovered_by: Agent or tool that discovered it
            parameters: Optional list of parameters
            technology_hints: Optional technology indicators
            priority: Priority level (high, medium, low)

        Returns:
            The created AttackSurface object
        """
        ...

    def add_finding(
        self,
        finding_id: str,
        title: str,
        severity: str,
        status: str,
        description: str,
        evidence: str,
        discovered_by: str,
        attack_surface_id: str | None = None,
        reproduction_steps: list[str] | None = None,
        remediation: str = "",
        validated_by: str | None = None,
    ) -> Any:
        """
        Add a new security finding to the findings document.

        Args:
            finding_id: Unique identifier (UUID)
            title: Short descriptive title
            severity: Severity level (critical, high, medium, low, info)
            status: Confirmation status (suspected, confirmed, false_positive, needs_manual)
            description: Detailed description
            evidence: Supporting evidence
            discovered_by: Agent or tool that discovered it
            attack_surface_id: Optional ID of related attack surface
            reproduction_steps: Optional reproduction steps
            remediation: Optional remediation guidance
            validated_by: Optional validator

        Returns:
            The created Finding object
        """
        ...

    def mark_surface_tested(self, surface_id: str) -> bool:
        """
        Mark an attack surface as tested.

        Args:
            surface_id: ID of the surface to mark

        Returns:
            True if surface was found and updated, False otherwise
        """
        ...

    def update_recon_summary(
        self,
        total_endpoints: int | None = None,
        total_forms: int | None = None,
        total_apis: int | None = None,
        technologies_detected: list[str] | None = None,
        authentication_mechanisms: list[str] | None = None,
        notes: str | None = None,
    ) -> Any:
        """
        Update or create the reconnaissance summary.

        Args:
            total_endpoints: Number of endpoints discovered
            total_forms: Number of forms found
            total_apis: Number of API endpoints
            technologies_detected: List of detected technologies
            authentication_mechanisms: List of auth mechanisms
            notes: General observations

        Returns:
            The updated ReconSummary object
        """
        ...

    def get_summary(self) -> dict:
        """
        Get a summary of the findings document.

        Returns:
            Dictionary with summary statistics
        """
        ...

    def get_untested_surfaces(self) -> list[Any]:
        """
        Get all attack surfaces that haven't been tested yet.

        Returns:
            List of untested attack surfaces
        """
        ...

    def get_all_findings(self) -> list[Any]:
        """
        Get all findings.

        Returns:
            List of all finding objects
        """
        ...

    def get_all_surfaces(self) -> list[Any]:
        """
        Get all attack surfaces.

        Returns:
            List of all attack surface objects
        """
        ...


class AsyncFindingsUpdater(Protocol):
    """
    Protocol for async-safe findings updates during parallel subagent execution.

    This extends FindingsUpdater with async methods that use locking to ensure
    thread-safe concurrent access. Use these methods when multiple subagents
    may be updating the findings document simultaneously.
    """

    async def add_attack_surface_async(
        self,
        surface_id: str,
        surface_type: str,
        url: str,
        description: str,
        discovered_by: str,
        parameters: list[str] | None = None,
        technology_hints: list[str] | None = None,
        priority: str = "medium",
    ) -> Any:
        """Add a new attack surface with async locking."""
        ...

    async def add_finding_async(
        self,
        finding_id: str,
        title: str,
        severity: str,
        status: str,
        description: str,
        evidence: str,
        discovered_by: str,
        attack_surface_id: str | None = None,
        reproduction_steps: list[str] | None = None,
        remediation: str = "",
        validated_by: str | None = None,
    ) -> Any:
        """Add a new finding with async locking."""
        ...

    async def mark_surface_tested_async(self, surface_id: str) -> bool:
        """Mark a surface as tested with async locking."""
        ...

    async def save_async(self, file_path: str | None = None) -> None:
        """Save findings with async locking."""
        ...

    async def add_agent_invocation_async(self, agent_name: str) -> None:
        """Record agent invocation with async locking."""
        ...

    async def increment_steps_async(self, count: int = 1) -> None:
        """Increment step count with async locking."""
        ...


class AgentDefinition(Protocol):
    """
    Protocol for modular agent definitions.
    
    Agent definitions encapsulate the configuration for a specific type of agent:
    - What model to use
    - Which tools to register
    - How to build prompts and objectives
    
    This enables a single unified runner that can load and execute different
    agent types based on CLI arguments.
    
    Example:
        class ReconAgent:
            name = "recon"
            description = "Reconnaissance agent for target discovery"
            model = "anthropic/claude-sonnet-4-20250514"
            
            def create_tools(self, context, container=None, **kwargs):
                tools = ToolRegistry()
                tools.register(ShellTool(container))
                # ...
                return tools
    """
    
    @property
    def name(self) -> str:
        """Unique identifier for this agent (e.g., 'recon', 'test_cycle')."""
        ...
    
    @property
    def description(self) -> str:
        """Human-readable description of what this agent does."""
        ...
    
    @property
    def model(self) -> str:
        """LLM model to use (e.g., 'anthropic/claude-sonnet-4-20250514')."""
        ...
    
    def create_tools(
        self,
        context: Any,
        container: Any | None = None,
        **kwargs: Any,
    ) -> Any:
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
        prompts: Any,
        tool_schemas: list[dict],
        scope_description: str,
    ) -> str:
        """
        Build the system prompt for this agent.
        
        Args:
            prompts: PromptBuilder instance
            tool_schemas: List of tool schemas in OpenAI format
            scope_description: Scope/limits for testing
            
        Returns:
            Formatted system prompt string
        """
        ...
    
    def build_objective(self, target: str, **kwargs: Any) -> str:
        """
        Build the user objective from runtime parameters.

        Args:
            target: Primary target (URL, path, etc.)
            **kwargs: Additional agent-specific parameters

        Returns:
            Formatted objective string
        """
        ...


class SubagentDispatcher(Protocol):
    """
    Protocol for components that can dispatch subagents.

    This allows the orchestrator to delegate work to specialized subagents
    (ReconSubagent, TestSubagent) while maintaining a clean interface.
    """

    async def dispatch(
        self,
        subagent_type: str,
        objective: str,
        focus_area: str = "",
        max_steps: int = 50,
    ) -> dict[str, Any]:
        """
        Dispatch a subagent to perform a specific task.

        Args:
            subagent_type: Type of subagent to dispatch ("recon" or "test")
            objective: The objective for the subagent to accomplish
            focus_area: Optional specific area to focus on
            max_steps: Maximum steps the subagent can take

        Returns:
            Dictionary with subagent results:
                - success: bool
                - summary: str
                - surfaces_added: int (for recon)
                - findings_added: int (for test)
                - steps_taken: int
                - error: str | None
        """
        ...
