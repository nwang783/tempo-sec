"""
Context module for Tempo Sec.

Exports:
    - ContextFrame: Snapshot of agent context at a point in time
    - Message: A single message in the conversation
    - MessageRole: Enum for message roles
    - ToolCall: Record of a tool invocation
    - AgentState: Working memory for the agent
    - ContextStore: Main context management interface
    - BranchManager: Parallel exploration support
    - BranchResult: Result from branch execution
"""

from tempo.context.frame import (
    AgentState,
    ContextFrame,
    Message,
    MessageRole,
    ToolCall,
)
from tempo.context.store import ContextStore
from tempo.context.branch import BranchManager, BranchResult
from tempo.context.persistence import (
    ContextTreeData,
    save_context_tree,
    load_context_tree,
    list_sessions,
    delete_session,
)

__all__ = [
    # Frame data classes
    "AgentState",
    "ContextFrame",
    "Message",
    "MessageRole",
    "ToolCall",
    # Store
    "ContextStore",
    # Branching
    "BranchManager",
    "BranchResult",
    # Persistence
    "ContextTreeData",
    "save_context_tree",
    "load_context_tree",
    "list_sessions",
    "delete_session",
]
