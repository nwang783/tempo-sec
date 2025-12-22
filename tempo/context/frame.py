"""
Context frame data models for Tempo Sec.

These data classes represent the core context tree structure,
including messages, tool calls, agent state, and frames.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
import uuid


class MessageRole(str, Enum):
    """Roles for messages in the conversation."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL_RESULT = "tool_result"


@dataclass
class Message:
    """A single message in the conversation."""
    role: MessageRole
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        """Deserialize from dictionary."""
        return cls(
            role=MessageRole(data["role"]),
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ToolCall:
    """Record of a tool invocation."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tool_name: str = ""
    input: dict[str, Any] = field(default_factory=dict)
    raw_output: str = ""                    # Original output (preserved for reference)
    summary: str | None = None              # Compressed version (used in context if set)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    duration_ms: int = 0
    success: bool = True
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)  # Tool-specific metadata
    
    @property
    def output_for_context(self) -> str:
        """Returns summary if available, otherwise raw output."""
        return self.summary if self.summary is not None else self.raw_output
    
    @property
    def tokens_saved(self) -> int:
        """Approximate tokens saved by summarization."""
        if self.summary is None:
            return 0
        # Rough estimate: 4 chars per token
        return (len(self.raw_output) - len(self.summary)) // 4
    
    def get_truncated_output(self, max_chars: int = 10000) -> str:
        """
        Get output for context, truncated to max_chars if necessary.
        
        Shows first max_chars with range info and instructions for viewing more.
        
        Args:
            max_chars: Maximum characters to include
            
        Returns:
            Truncated output with range indicator, or full output if short enough
        """
        output = self.summary if self.summary is not None else self.raw_output
        total = len(output)
        
        if total <= max_chars:
            return output
        
        # Show first max_chars with range info
        return (
            f"[Showing chars 0-{max_chars} of {total} total]\n"
            f"{output[:max_chars]}\n\n"
            f"[Output truncated. Use view_tool_output(tool_call_id='{self.id}', "
            f"start_char=N, end_char=M) to view other ranges.]"
        )
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "tool_name": self.tool_name,
            "input": self.input,
            "raw_output": self.raw_output,
            "summary": self.summary,
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": self.duration_ms,
            "success": self.success,
            "error": self.error,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "ToolCall":
        """Deserialize from dictionary."""
        return cls(
            id=data["id"],
            tool_name=data["tool_name"],
            input=data["input"],
            raw_output=data["raw_output"],
            summary=data.get("summary"),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            duration_ms=data["duration_ms"],
            success=data["success"],
            error=data.get("error"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class AgentState:
    """Working memory for the agent - hypotheses, notes, findings."""
    current_phase: str = "recon"
    hypotheses: list[dict[str, Any]] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    test_plan: list[dict[str, Any]] = field(default_factory=list)  # Checklist items
    custom: dict[str, Any] = field(default_factory=dict)  # Extensible state
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "current_phase": self.current_phase,
            "hypotheses": self.hypotheses,
            "findings": self.findings,
            "notes": self.notes,
            "test_plan": self.test_plan,
            "custom": self.custom,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "AgentState":
        """Deserialize from dictionary."""
        return cls(
            current_phase=data.get("current_phase", "recon"),
            hypotheses=data.get("hypotheses", []),
            findings=data.get("findings", []),
            notes=data.get("notes", []),
            test_plan=data.get("test_plan", []),
            custom=data.get("custom", {}),
        )


@dataclass
class ContextFrame:
    """
    A snapshot of the agent's context at a point in time.
    Forms nodes in the context tree.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_id: str | None = None            # None for root frame
    created_at: datetime = field(default_factory=datetime.utcnow)
    messages: list[Message] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    state: AgentState = field(default_factory=AgentState)
    
    # Metadata
    label: str = ""                         # Optional human-readable label
    is_checkpoint: bool = False             # Marked as explicit checkpoint
    is_branch_point: bool = False           # Has multiple children
    branch_objective: str | None = None     # If this is a branch, what's its goal?
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "parent_id": self.parent_id,
            "created_at": self.created_at.isoformat(),
            "messages": [m.to_dict() for m in self.messages],
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "state": self.state.to_dict(),
            "label": self.label,
            "is_checkpoint": self.is_checkpoint,
            "is_branch_point": self.is_branch_point,
            "branch_objective": self.branch_objective,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "ContextFrame":
        """Deserialize from dictionary."""
        return cls(
            id=data["id"],
            parent_id=data.get("parent_id"),
            created_at=datetime.fromisoformat(data["created_at"]),
            messages=[Message.from_dict(m) for m in data["messages"]],
            tool_calls=[ToolCall.from_dict(tc) for tc in data["tool_calls"]],
            state=AgentState.from_dict(data["state"]),
            label=data.get("label", ""),
            is_checkpoint=data.get("is_checkpoint", False),
            is_branch_point=data.get("is_branch_point", False),
            branch_objective=data.get("branch_objective"),
        )
