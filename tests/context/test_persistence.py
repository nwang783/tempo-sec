"""Tests for tempo/context/persistence.py."""

import json
import os
import tempfile
from datetime import datetime

import pytest

from tempo.context.frame import ContextFrame, Message, MessageRole
from tempo.context.persistence import (
    ContextTreeData,
    delete_session,
    list_sessions,
    load_context_tree,
    save_context_tree,
)


class TestContextTreeData:
    """Tests for ContextTreeData dataclass."""
    
    def test_to_dict(self):
        """Test serialization to dictionary."""
        data = ContextTreeData(
            session_id="test-session",
            created_at=datetime(2024, 1, 15, 10, 30),
            updated_at=datetime(2024, 1, 15, 11, 30),
            current_frame_id="frame-123",
            frames={"frame-123": {"id": "frame-123"}},
            metadata={"key": "value"},
        )
        
        result = data.to_dict()
        
        assert result["session_id"] == "test-session"
        assert result["current_frame_id"] == "frame-123"
        assert "2024-01-15" in result["created_at"]
    
    def test_roundtrip(self):
        """Test serialization/deserialization roundtrip."""
        original = ContextTreeData(
            session_id="test-session",
            created_at=datetime(2024, 1, 15, 10, 30),
            updated_at=datetime(2024, 1, 15, 11, 30),
            current_frame_id="frame-123",
            frames={"frame-123": {"id": "frame-123"}},
            metadata={"key": "value"},
        )
        
        restored = ContextTreeData.from_dict(original.to_dict())
        
        assert restored.session_id == original.session_id
        assert restored.current_frame_id == original.current_frame_id


class TestSaveLoadContextTree:
    """Tests for save/load functions."""
    
    def test_save_and_load(self):
        """Test saving and loading a context tree."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a frame
            frame = ContextFrame()
            frame.messages.append(Message(
                role=MessageRole.USER,
                content="Hello, agent!",
            ))
            
            # Save
            path = save_context_tree(
                session_id="test-save",
                frames={frame.id: frame},
                current_frame_id=frame.id,
                persistence_dir=tmpdir,
            )
            
            assert os.path.exists(path)
            
            # Load
            loaded_frames, current_id, tree_data = load_context_tree(path)
            
            assert current_id == frame.id
            assert frame.id in loaded_frames
            assert loaded_frames[frame.id].messages[0].content == "Hello, agent!"
    
    def test_save_updates_timestamp(self):
        """Test that saving updates the timestamp."""
        with tempfile.TemporaryDirectory() as tmpdir:
            frame = ContextFrame()
            
            # First save
            path = save_context_tree(
                session_id="test-timestamp",
                frames={frame.id: frame},
                current_frame_id=frame.id,
                persistence_dir=tmpdir,
            )
            
            with open(path) as f:
                first_save = json.load(f)
            
            # Second save
            save_context_tree(
                session_id="test-timestamp",
                frames={frame.id: frame},
                current_frame_id=frame.id,
                persistence_dir=tmpdir,
            )
            
            with open(path) as f:
                second_save = json.load(f)
            
            # Created should be same, updated should be newer
            assert first_save["created_at"] == second_save["created_at"]
            assert second_save["updated_at"] >= first_save["updated_at"]


class TestListSessions:
    """Tests for list_sessions function."""
    
    def test_list_empty_dir(self):
        """Test listing sessions in empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions = list_sessions(tmpdir)
            assert sessions == []
    
    def test_list_sessions(self):
        """Test listing saved sessions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create two sessions
            for session_id in ["session-a", "session-b"]:
                frame = ContextFrame()
                save_context_tree(
                    session_id=session_id,
                    frames={frame.id: frame},
                    current_frame_id=frame.id,
                    persistence_dir=tmpdir,
                )
            
            sessions = list_sessions(tmpdir)
            
            assert len(sessions) == 2
            session_ids = [s[0] for s in sessions]
            assert "session-a" in session_ids
            assert "session-b" in session_ids


class TestDeleteSession:
    """Tests for delete_session function."""
    
    def test_delete_existing(self):
        """Test deleting an existing session."""
        with tempfile.TemporaryDirectory() as tmpdir:
            frame = ContextFrame()
            path = save_context_tree(
                session_id="to-delete",
                frames={frame.id: frame},
                current_frame_id=frame.id,
                persistence_dir=tmpdir,
            )
            
            assert os.path.exists(path)
            
            result = delete_session("to-delete", tmpdir)
            
            assert result is True
            assert not os.path.exists(path)
    
    def test_delete_nonexistent(self):
        """Test deleting a non-existent session."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = delete_session("nonexistent", tmpdir)
            assert result is False
