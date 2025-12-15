"""
Agent module for Tempo Sec.

Exports:
    - AgentConfig: Agent configuration dataclass
    - BranchCoordinator: Manages agent-initiated branching
    - SubtaskResult: Result from a subtask
"""

from tempo.agent.config import AgentConfig
from tempo.agent.branch_coordinator import (
    BranchCoordinator,
    SubtaskResult,
    PendingBranch,
)

__all__ = [
    "AgentConfig",
    "BranchCoordinator",
    "SubtaskResult",
    "PendingBranch",
]
