"""
Subagent Tracker.

Tracks subagent lifecycle and aggregates statistics for visualization.
Follows the project's dependency rules - lives in visualization/, no imports
from tools/prompts/context.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tempo.context.store import ContextStore


class SubagentStatus(str, Enum):
    """Status of a subagent run."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class SubagentState:
    """State for a single subagent run."""
    id: str
    type: str
    objective: str
    status: SubagentStatus = SubagentStatus.QUEUED
    steps: int = 0
    findings_count: int = 0
    surfaces_count: int = 0
    summary: str = ""
    context: "ContextStore | None" = None


@dataclass
class SubagentTracker:
    """Tracks all subagent runs for the current orchestrator session."""
    
    subagents: dict[str, SubagentState] = field(default_factory=dict)
    
    def register(self, subagent_id: str, subagent_type: str, objective: str) -> None:
        """Register a new subagent.
        
        Args:
            subagent_id: Unique identifier for this subagent run
            subagent_type: Type of subagent (e.g., "recon", "test")
            objective: What the subagent should accomplish
        """
        self.subagents[subagent_id] = SubagentState(
            id=subagent_id,
            type=subagent_type,
            objective=objective,
            status=SubagentStatus.RUNNING,
        )
    
    def update_status(self, subagent_id: str, status: SubagentStatus) -> None:
        """Update a subagent's status.
        
        Args:
            subagent_id: The subagent to update
            status: New status
        """
        if subagent_id in self.subagents:
            self.subagents[subagent_id].status = status
    
    def complete(
        self,
        subagent_id: str,
        success: bool,
        summary: str,
        findings_count: int,
        surfaces_count: int,
    ) -> None:
        """Mark a subagent as complete.
        
        Args:
            subagent_id: The subagent to complete
            success: Whether the subagent completed successfully
            summary: Summary of what was accomplished
            findings_count: Number of findings added
            surfaces_count: Number of attack surfaces added
        """
        if subagent_id in self.subagents:
            subagent = self.subagents[subagent_id]
            subagent.status = SubagentStatus.COMPLETE if success else SubagentStatus.FAILED
            subagent.summary = summary
            subagent.findings_count = findings_count
            subagent.surfaces_count = surfaces_count
    
    def increment_steps(self, subagent_id: str) -> None:
        """Increment step count for a subagent.
        
        Args:
            subagent_id: The subagent to update
        """
        if subagent_id in self.subagents:
            self.subagents[subagent_id].steps += 1
    
    def to_list(self) -> list[dict]:
        """Export subagent states as list of dicts for API.
        
        Returns:
            List of subagent state dictionaries
        """
        return [
            {
                "id": s.id,
                "type": s.type,
                "objective": s.objective,
                "status": s.status.value,
                "steps": s.steps,
                "findings": s.findings_count,
                "surfaces": s.surfaces_count,
                "summary": s.summary,
            }
            for s in self.subagents.values()
        ]
    
    def clear(self) -> None:
        """Clear all tracked subagents."""
        self.subagents.clear()
