"""Tests for tempo/context/frame.py data models."""

from datetime import datetime

import pytest

from tempo.context.frame import (
    AgentState,
    ContextFrame,
    Message,
    MessageRole,
    ToolCall,
)


class TestMessage:
    """Tests for Message dataclass."""
    
    def test_create_message(self):
        """Test basic message creation."""
        msg = Message(role=MessageRole.USER, content="Hello, agent!")
        
        assert msg.role == MessageRole.USER
        assert msg.content == "Hello, agent!"
        assert isinstance(msg.timestamp, datetime)
        assert msg.metadata == {}
    
    def test_message_to_dict(self):
        """Test serialization to dictionary."""
        msg = Message(
            role=MessageRole.ASSISTANT,
            content="Hello, user!",
            metadata={"key": "value"},
        )
        
        data = msg.to_dict()
        
        assert data["role"] == "assistant"
        assert data["content"] == "Hello, user!"
        assert data["metadata"] == {"key": "value"}
        assert "timestamp" in data
    
    def test_message_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "role": "system",
            "content": "You are a helpful assistant.",
            "timestamp": "2024-01-15T10:30:00",
            "metadata": {"test": True},
        }
        
        msg = Message.from_dict(data)
        
        assert msg.role == MessageRole.SYSTEM
        assert msg.content == "You are a helpful assistant."
        assert msg.timestamp == datetime.fromisoformat("2024-01-15T10:30:00")
        assert msg.metadata == {"test": True}
    
    def test_message_roundtrip(self):
        """Test serialization/deserialization roundtrip."""
        original = Message(
            role=MessageRole.TOOL_RESULT,
            content="Tool output here",
            metadata={"tool_id": "123"},
        )
        
        restored = Message.from_dict(original.to_dict())
        
        assert restored.role == original.role
        assert restored.content == original.content
        assert restored.metadata == original.metadata


class TestToolCall:
    """Tests for ToolCall dataclass."""
    
    def test_create_tool_call(self):
        """Test basic tool call creation."""
        tc = ToolCall(
            tool_name="shell",
            input={"command": "ls -la"},
            raw_output="total 0\ndrwxr-xr-x  2 user user 40 Jan 15 10:30 .",
        )
        
        assert tc.tool_name == "shell"
        assert tc.input == {"command": "ls -la"}
        assert tc.success is True
        assert tc.summary is None
    
    def test_output_for_context_raw(self):
        """Test output_for_context returns raw output when no summary."""
        tc = ToolCall(
            tool_name="shell",
            raw_output="raw output here",
        )
        
        assert tc.output_for_context == "raw output here"
    
    def test_output_for_context_summary(self):
        """Test output_for_context returns summary when available."""
        tc = ToolCall(
            tool_name="shell",
            raw_output="very long raw output that would waste tokens",
            summary="Files listed successfully",
        )
        
        assert tc.output_for_context == "Files listed successfully"
    
    def test_tokens_saved(self):
        """Test tokens saved calculation."""
        tc = ToolCall(
            tool_name="shell",
            raw_output="A" * 100,  # 100 chars = ~25 tokens
            summary="B" * 20,      # 20 chars = ~5 tokens
        )
        
        # (100 - 20) // 4 = 20 tokens saved
        assert tc.tokens_saved == 20
    
    def test_tokens_saved_no_summary(self):
        """Test tokens saved is 0 when no summary."""
        tc = ToolCall(tool_name="shell", raw_output="output")
        
        assert tc.tokens_saved == 0
    
    def test_tool_call_roundtrip(self):
        """Test serialization/deserialization roundtrip."""
        original = ToolCall(
            tool_name="browser",
            input={"url": "https://example.com"},
            raw_output="<html>...</html>",
            summary="HTML page",
            duration_ms=150,
            success=True,
        )
        
        restored = ToolCall.from_dict(original.to_dict())
        
        assert restored.id == original.id
        assert restored.tool_name == original.tool_name
        assert restored.input == original.input
        assert restored.raw_output == original.raw_output
        assert restored.summary == original.summary
    
    def test_truncated_output_includes_instruction_within_limit(self):
        """Test that truncated output includes summarization instruction within limit."""
        long_output = "A" * 20000
        tc = ToolCall(tool_name="test", raw_output=long_output)
        
        result = tc.get_truncated_output(max_chars=10000)
        
        # Verify total length doesn't exceed limit
        assert len(result) <= 10000, f"Result length {len(result)} exceeds limit 10000"
        # Verify instruction is included
        assert "OUTPUT TRUNCATED" in result
        assert "MUST call summarize_previous_tool_output" in result
        assert tc.id in result
        assert "view_tool_output" in result
    
    def test_short_output_not_truncated(self):
        """Test that short outputs are not modified."""
        short_output = "Short output"
        tc = ToolCall(tool_name="test", raw_output=short_output)
        
        result = tc.get_truncated_output(max_chars=10000)
        
        assert result == short_output
        assert "TRUNCATED" not in result


class TestAgentState:
    """Tests for AgentState dataclass."""
    
    def test_default_state(self):
        """Test default agent state."""
        state = AgentState()
        
        assert state.hypotheses == []
        assert state.findings == []
        assert state.notes == []
        assert state.custom == {}
    
    def test_state_roundtrip(self):
        """Test serialization/deserialization roundtrip."""
        original = AgentState(
            hypotheses=[{"id": 1, "desc": "SQL injection on login"}],
            findings=[{"vuln": "XSS", "severity": "high"}],
            notes=["Check auth endpoints"],
            custom={"last_url": "https://example.com"},
        )
        
        restored = AgentState.from_dict(original.to_dict())
        
        assert restored.hypotheses == original.hypotheses
        assert restored.findings == original.findings
        assert restored.notes == original.notes
        assert restored.custom == original.custom


class TestContextFrame:
    """Tests for ContextFrame dataclass."""
    
    def test_create_frame(self):
        """Test basic frame creation."""
        frame = ContextFrame()
        
        assert frame.id is not None
        assert frame.parent_id is None
        assert frame.messages == []
        assert frame.tool_calls == []
        assert isinstance(frame.state, AgentState)
    
    def test_frame_with_content(self):
        """Test frame with messages and tool calls."""
        frame = ContextFrame(
            messages=[
                Message(role=MessageRole.USER, content="Scan example.com"),
            ],
            tool_calls=[
                ToolCall(tool_name="shell", input={"command": "nmap example.com"}),
            ],
            label="Initial recon",
            is_checkpoint=True,
        )
        
        assert len(frame.messages) == 1
        assert len(frame.tool_calls) == 1
        assert frame.label == "Initial recon"
        assert frame.is_checkpoint is True
    
    def test_frame_roundtrip(self):
        """Test serialization/deserialization roundtrip."""
        original = ContextFrame(
            parent_id="parent-123",
            messages=[
                Message(role=MessageRole.SYSTEM, content="You are Tempo Sec"),
            ],
            tool_calls=[
                ToolCall(tool_name="file_read", input={"path": "/etc/passwd"}),
            ],
            state=AgentState(),
            label="After recon",
            is_branch_point=True,
            branch_objective="Test SQL injection",
        )
        
        restored = ContextFrame.from_dict(original.to_dict())
        
        assert restored.id == original.id
        assert restored.parent_id == original.parent_id
        assert len(restored.messages) == 1
        assert len(restored.tool_calls) == 1
        assert restored.label == original.label
        assert restored.is_branch_point is True
        assert restored.branch_objective == "Test SQL injection"
