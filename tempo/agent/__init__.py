"""
Agent module for Tempo Sec.

Exports:
    - AgentConfig: Agent configuration dataclass
    - BranchCoordinator: Manages agent-initiated branching
    - SubtaskResult: Result from a subtask
    - OutputSummarizer: Tool output summarization
    - StepHandler: Handles individual step execution
    - SpecialToolResult: Result from processing special tools
    - EventBus: Pub/sub for agent events
    - AgentEvent: Event data structure
    - Agent: Main agent runner
    - AgentResult: Final result of an agent run
    - StepResult: Result of a single step
"""

from tempo.agent.config import AgentConfig
from tempo.agent.branch_coordinator import (
    BranchCoordinator,
    SubtaskResult,
    PendingBranch,
)
from tempo.agent.summarizer import OutputSummarizer
from tempo.agent.step_handler import StepHandler, SpecialToolResult
from tempo.agent.event_bus import EventBus, AgentEvent
from tempo.agent.runner import Agent, AgentResult, StepResult

__all__ = [
    "AgentConfig",
    "BranchCoordinator",
    "SubtaskResult",
    "PendingBranch",
    "OutputSummarizer",
    "StepHandler",
    "SpecialToolResult",
    "EventBus",
    "AgentEvent",
    "Agent",
    "AgentResult",
    "StepResult",
]
