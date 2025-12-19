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


class PhaseTransitioner(Protocol):
    """Protocol for components that can transition workflow phases."""
    
    def transition(self, phase: str) -> bool:
        """
        Transition to a new workflow phase.
        
        Args:
            phase: Target phase name (recon, hypothesize, test, reflect)
            
        Returns:
            True if transition succeeded
        """
        ...
    
    @property
    def current_phase(self) -> str:
        """Get the current phase name."""
        ...


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
