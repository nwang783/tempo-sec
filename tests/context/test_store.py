"""Tests for tempo/context/store.py."""

import tempfile
from datetime import datetime

import pytest

from tempo.context.frame import MessageRole, ToolCall
from tempo.context.store import ContextStore


class TestContextStoreBasics:
    """Tests for basic ContextStore operations."""
    
    def test_create_store(self):
        """Test creating a new context store."""
        store = ContextStore()
        
        assert store.session_id is not None
        assert store.current_frame is not None
    
    def test_add_message(self):
        """Test adding a message."""
        store = ContextStore()
        store.add_message(MessageRole.USER, "Hello, agent!")
        
        assert len(store.current_frame.messages) == 1
        assert store.current_frame.messages[0].content == "Hello, agent!"
        assert store.current_frame.messages[0].role == MessageRole.USER
    
    def test_add_tool_call(self):
        """Test adding a tool call."""
        store = ContextStore()
        tc = ToolCall(
            tool_name="shell",
            input={"command": "ls"},
            raw_output="file1.txt\nfile2.txt",
        )
        store.add_tool_call(tc)
        
        assert len(store.current_frame.tool_calls) == 1
        assert store.current_frame.tool_calls[0].tool_name == "shell"


class TestStateManagement:
    """Tests for state management."""
    
    def test_get_state(self):
        """Test getting current state."""
        store = ContextStore()
        state = store.get_state()
        
        assert state.current_phase == "recon"
        assert state.hypotheses == []
    
    def test_update_state(self):
        """Test updating state."""
        store = ContextStore()
        store.update_state(
            current_phase="hypothesize",
            hypotheses=[{"id": 1, "desc": "SQL injection"}],
        )
        
        state = store.get_state()
        assert state.current_phase == "hypothesize"
        assert len(state.hypotheses) == 1


class TestCheckpointing:
    """Tests for checkpointing operations."""
    
    def test_checkpoint(self):
        """Test creating a checkpoint."""
        store = ContextStore()
        store.add_message(MessageRole.USER, "First message")
        
        checkpoint_id = store.checkpoint("initial")
        
        assert checkpoint_id == store.current_frame.id
        assert store.current_frame.is_checkpoint is True
        assert store.current_frame.label == "initial"
    
    def test_list_checkpoints(self):
        """Test listing checkpoints."""
        store = ContextStore()
        
        # First checkpoint
        store.checkpoint("first")
        
        # Create a new frame by reverting (which creates a new branch)
        first_id = store.current_frame.id
        store.revert(first_id)
        
        # Second checkpoint on new frame
        store.checkpoint("second")
        
        checkpoints = store.list_checkpoints()
        
        # Should have 2 checkpoints (first and second)
        assert len(checkpoints) == 2
        labels = [c[1] for c in checkpoints]
        assert "first" in labels
        assert "second" in labels
    
    def test_revert(self):
        """Test reverting to checkpoint."""
        store = ContextStore()
        store.add_message(MessageRole.USER, "First")
        checkpoint_id = store.checkpoint("checkpoint")
        
        store.add_message(MessageRole.USER, "Second")
        assert len(store.current_frame.messages) == 2
        
        store.revert(checkpoint_id)
        
        # After revert, we're on a new frame with parent = checkpoint
        assert store.current_frame.parent_id == checkpoint_id
        # State should be copied from checkpoint
        assert len(store.current_frame.messages) == 0  # New frame, no messages yet


class TestBranching:
    """Tests for branching operations."""
    
    def test_branch(self):
        """Test creating branches."""
        store = ContextStore()
        store.add_message(MessageRole.USER, "Setup")
        
        branch_ids = store.branch(3, objectives=["A", "B", "C"])
        
        assert len(branch_ids) == 3
        assert store.current_frame.is_branch_point is True
    
    def test_switch_to_branch(self):
        """Test switching between branches."""
        store = ContextStore()
        branch_ids = store.branch(2, objectives=["X", "Y"])
        
        store.switch_to_branch(branch_ids[0])
        assert store.current_frame.id == branch_ids[0]
        assert store.current_frame.branch_objective == "X"
        
        store.switch_to_branch(branch_ids[1])
        assert store.current_frame.id == branch_ids[1]
        assert store.current_frame.branch_objective == "Y"
    
    def test_get_branch_ids(self):
        """Test getting sibling branch IDs."""
        store = ContextStore()
        branch_ids = store.branch(3)
        
        store.switch_to_branch(branch_ids[0])
        siblings = store.get_branch_ids()
        
        assert set(siblings) == set(branch_ids)
    
    def test_merge_branches(self):
        """Test merging branches."""
        store = ContextStore()
        parent_id = store.current_frame.id
        branch_ids = store.branch(2, objectives=["A", "B"])
        
        # Add content to each branch
        for i, bid in enumerate(branch_ids):
            store.switch_to_branch(bid)
            store.add_message(MessageRole.ASSISTANT, f"Branch {i} result")
        
        # Merge
        store.merge_branches(branch_ids, ["Summary A", "Summary B"])
        
        # Should be on a new merge frame
        assert store.current_frame.parent_id == parent_id
        assert len(store.current_frame.messages) == 2


class TestContextRendering:
    """Tests for context rendering."""
    
    def test_render_messages(self):
        """Test rendering messages."""
        store = ContextStore()
        store.add_message(MessageRole.SYSTEM, "You are an agent")
        store.add_message(MessageRole.USER, "Hello")
        store.add_message(MessageRole.ASSISTANT, "Hi there")
        
        messages = store.render_messages()
        
        assert len(messages) == 3
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[2]["role"] == "assistant"
    
    def test_render_without_system(self):
        """Test rendering without system messages."""
        store = ContextStore()
        store.add_message(MessageRole.SYSTEM, "You are an agent")
        store.add_message(MessageRole.USER, "Hello")
        
        messages = store.render_messages(include_system=False)
        
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
    
    def test_render_with_tool_calls(self):
        """Test rendering includes tool calls."""
        store = ContextStore()
        store.add_message(MessageRole.USER, "Run a command")
        store.add_tool_call(ToolCall(
            tool_name="shell",
            input={"command": "ls"},
            raw_output="file.txt",
        ))
        
        messages = store.render_messages()
        
        # User message + tool call (as assistant) + tool result (as user)
        assert len(messages) == 3
    
    def test_estimate_tokens(self):
        """Test token estimation."""
        store = ContextStore()
        store.add_message(MessageRole.USER, "A" * 400)  # ~100 tokens
        
        tokens = store.estimate_tokens()
        
        assert tokens > 0
        assert tokens < 200  # Reasonable estimate


class TestPersistence:
    """Tests for save/load operations."""
    
    def test_save_and_load(self):
        """Test saving and loading a context store."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create and populate store
            store = ContextStore(persistence_dir=tmpdir)
            store.add_message(MessageRole.USER, "Test message")
            store.update_state(current_phase="test")
            
            # Save
            path = store.save()
            
            # Load
            loaded = ContextStore.load(path)
            
            assert loaded.session_id == store.session_id
            messages = loaded.render_messages()
            assert len(messages) == 1
            assert messages[0]["content"] == "Test message"


class TestSummarization:
    """Tests for tool call summarization."""
    
    def test_summarize_tool_call(self):
        """Test summarizing a tool call."""
        store = ContextStore()
        tc = ToolCall(
            tool_name="shell",
            raw_output="Very long output " * 100,
        )
        store.add_tool_call(tc)
        
        store.summarize_tool_call(tc.id, "Short summary")
        
        assert tc.summary == "Short summary"
        assert tc.output_for_context == "Short summary"
    
    def test_summarize_nonexistent(self):
        """Test summarizing non-existent tool call."""
        store = ContextStore()
        
        with pytest.raises(KeyError):
            store.summarize_tool_call("nonexistent-id", "Summary")
