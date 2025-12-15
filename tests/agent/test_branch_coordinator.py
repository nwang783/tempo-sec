"""Tests for tempo/agent/branch_coordinator.py."""

import pytest

from tempo.agent.branch_coordinator import (
    BranchCoordinator,
    SubtaskResult,
    PendingBranch,
)
from tempo.context.store import ContextStore


class TestSubtaskResult:
    """Tests for SubtaskResult dataclass."""
    
    def test_create_success(self):
        """Test creating a successful result."""
        result = SubtaskResult(
            subtask_id="st-1",
            objective="Test XSS",
            summary="No XSS found",
        )
        
        assert result.success is True
        assert result.error is None
    
    def test_create_failure(self):
        """Test creating a failed result."""
        result = SubtaskResult(
            subtask_id="st-2",
            objective="Test SQLI",
            summary="Failed",
            success=False,
            error="Timeout",
        )
        
        assert result.success is False
        assert result.error == "Timeout"


class TestBranchCoordinator:
    """Tests for BranchCoordinator class."""
    
    def test_init(self):
        """Test initializing the coordinator."""
        store = ContextStore()
        coordinator = BranchCoordinator(store)
        
        assert coordinator.context is store
    
    @pytest.mark.asyncio
    async def test_spawn_subtasks(self):
        """Test spawning subtasks."""
        store = ContextStore()
        coordinator = BranchCoordinator(store)
        
        branch_id = await coordinator.spawn_subtasks([
            "Investigate login",
            "Check API endpoints",
        ])
        
        assert branch_id is not None
        assert branch_id in coordinator._pending_branches
        assert len(coordinator._pending_branches[branch_id].subtasks) == 2
    
    def test_record_subtask_result(self):
        """Test recording a subtask result."""
        store = ContextStore()
        coordinator = BranchCoordinator(store)
        
        # Create branches manually for testing
        branch_ids = store.branch(2, ["A", "B"])
        pending = PendingBranch(
            branch_id="test-branch",
            parent_frame_id=store.current_frame.parent_id,
            subtasks=["A", "B"],
            context_branch_ids=branch_ids,
        )
        coordinator._pending_branches["test-branch"] = pending
        
        # Record first result
        complete = coordinator.record_subtask_result(
            branch_id="test-branch",
            subtask_id=branch_ids[0],
            summary="Completed A",
        )
        assert complete is False
        
        # Record second result
        complete = coordinator.record_subtask_result(
            branch_id="test-branch",
            subtask_id=branch_ids[1],
            summary="Completed B",
        )
        assert complete is True
    
    def test_merge_results(self):
        """Test merging subtask results."""
        store = ContextStore()
        coordinator = BranchCoordinator(store)
        
        results = [
            SubtaskResult(
                subtask_id="1",
                objective="Test A",
                summary="A passed",
            ),
            SubtaskResult(
                subtask_id="2",
                objective="Test B",
                summary="B failed",
                success=False,
                error="Connection error",
            ),
        ]
        
        merged = coordinator.merge_results(results)
        
        assert "Test A" in merged
        assert "Test B" in merged
        assert "A passed" in merged
        assert "Connection error" in merged
        assert "✓" in merged  # Success marker
        assert "✗" in merged  # Failure marker
    
    def test_is_complete(self):
        """Test is_complete check."""
        store = ContextStore()
        coordinator = BranchCoordinator(store)
        
        # Non-existent branch is considered complete
        assert coordinator.is_complete("nonexistent") is True
    
    @pytest.mark.asyncio
    async def test_await_completion_timeout(self):
        """Test awaiting completion with timeout."""
        store = ContextStore()
        coordinator = BranchCoordinator(store)
        
        branch_id = await coordinator.spawn_subtasks(["Task"])
        
        # Should return immediately with timeout
        results = await coordinator.await_completion(branch_id, timeout=0.1)
        
        # No results yet since no executor was provided
        assert len(results) == 0
