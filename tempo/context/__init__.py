"""
Context module for Tempo Sec.

Exports:
    - ContextFrame: Single context snapshot
    - Message: Chat message
    - MessageRole: Message role enum
    - ToolCall: Tool invocation record
    - AgentState: Mutable agent state
    - ContextStore: Context tree management
    - BranchManager: Branch coordination
"""

from tempo.context.frame import (
    ContextFrame,
    Message,
    MessageRole,
    ToolCall,
    AgentState,
)
from tempo.context.store import ContextStore
from tempo.context.branch import BranchManager

__all__ = [
    "ContextFrame",
    "Message",
    "MessageRole",
    "ToolCall",
    "AgentState",
    "ContextStore",
    "BranchManager",
]
