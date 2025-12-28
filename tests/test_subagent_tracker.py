"""
Unit tests for SubagentTracker.

Tests for tracking subagent lifecycle and aggregating statistics.
"""

import pytest

from tempo.visualization.subagent_tracker import (
    SubagentTracker,
    SubagentStatus,
    SubagentState,
)


class TestSubagentStatus:
    """Tests for SubagentStatus enum."""
    
    def test_status_values(self):
        """Status enum has expected string values."""
        assert SubagentStatus.QUEUED.value == "queued"
        assert SubagentStatus.RUNNING.value == "running"
        assert SubagentStatus.COMPLETE.value == "complete"
        assert SubagentStatus.FAILED.value == "failed"


class TestSubagentState:
    """Tests for SubagentState dataclass."""
    
    def test_default_values(self):
        """SubagentState has correct default values."""
        state = SubagentState(id="test-1", type="recon", objective="Test")
        
        assert state.id == "test-1"
        assert state.type == "recon"
        assert state.objective == "Test"
        assert state.status == SubagentStatus.QUEUED
        assert state.steps == 0
        assert state.findings_count == 0
        assert state.surfaces_count == 0
        assert state.summary == ""
        assert state.context is None


class TestSubagentTracker:
    """Tests for SubagentTracker."""
    
    def test_register_creates_subagent(self):
        """register() creates a new subagent with running status."""
        tracker = SubagentTracker()
        tracker.register("sub-1", "recon", "Test objective")
        
        assert "sub-1" in tracker.subagents
        subagent = tracker.subagents["sub-1"]
        assert subagent.type == "recon"
        assert subagent.objective == "Test objective"
        assert subagent.status == SubagentStatus.RUNNING
    
    def test_update_status(self):
        """update_status() changes subagent status."""
        tracker = SubagentTracker()
        tracker.register("sub-1", "recon", "Test")
        
        tracker.update_status("sub-1", SubagentStatus.COMPLETE)
        
        assert tracker.subagents["sub-1"].status == SubagentStatus.COMPLETE
    
    def test_update_status_ignores_unknown(self):
        """update_status() silently ignores unknown subagent IDs."""
        tracker = SubagentTracker()
        # Should not raise
        tracker.update_status("unknown", SubagentStatus.COMPLETE)
    
    def test_complete_success(self):
        """complete() marks subagent as complete with stats."""
        tracker = SubagentTracker()
        tracker.register("sub-1", "recon", "Test")
        
        tracker.complete(
            "sub-1",
            success=True,
            summary="Found vulnerabilities",
            findings_count=5,
            surfaces_count=3,
        )
        
        subagent = tracker.subagents["sub-1"]
        assert subagent.status == SubagentStatus.COMPLETE
        assert subagent.summary == "Found vulnerabilities"
        assert subagent.findings_count == 5
        assert subagent.surfaces_count == 3
    
    def test_complete_failure(self):
        """complete() marks subagent as failed on unsuccessful completion."""
        tracker = SubagentTracker()
        tracker.register("sub-1", "test", "Test")
        
        tracker.complete(
            "sub-1",
            success=False,
            summary="Error occurred",
            findings_count=0,
            surfaces_count=0,
        )
        
        assert tracker.subagents["sub-1"].status == SubagentStatus.FAILED
    
    def test_increment_steps(self):
        """increment_steps() increases step count."""
        tracker = SubagentTracker()
        tracker.register("sub-1", "recon", "Test")
        
        tracker.increment_steps("sub-1")
        tracker.increment_steps("sub-1")
        
        assert tracker.subagents["sub-1"].steps == 2
    
    def test_to_list_empty(self):
        """to_list() returns empty list for empty tracker."""
        tracker = SubagentTracker()
        assert tracker.to_list() == []
    
    def test_to_list_exports_all(self):
        """to_list() exports all subagent states as dicts."""
        tracker = SubagentTracker()
        tracker.register("sub-1", "recon", "Obj 1")
        tracker.register("sub-2", "test", "Obj 2")
        
        result = tracker.to_list()
        
        assert len(result) == 2
        assert result[0]["id"] == "sub-1"
        assert result[0]["type"] == "recon"
        assert result[0]["status"] == "running"
        assert result[1]["id"] == "sub-2"
    
    def test_clear(self):
        """clear() removes all tracked subagents."""
        tracker = SubagentTracker()
        tracker.register("sub-1", "recon", "Test")
        tracker.register("sub-2", "test", "Test")
        
        tracker.clear()
        
        assert len(tracker.subagents) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
