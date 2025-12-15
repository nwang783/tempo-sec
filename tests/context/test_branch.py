"""Tests for tempo/context/branch.py."""

import pytest

from tempo.context.branch import BranchManager, BranchResult
from tempo.context.store import ContextStore


class TestBranchResult:
    """Tests for BranchResult dataclass."""
    
    def test_create_success(self):
        """Test creating a successful branch result."""
        result = BranchResult(
            branch_id="branch-123",
            objective="Test SQL injection",
            summary="Found vulnerability",
            steps_taken=5,
            success=True,
        )
        
        assert result.branch_id == "branch-123"
        assert result.success is True
        assert result.error is None
    
    def test_create_failure(self):
        """Test creating a failed branch result."""
        result = BranchResult(
            branch_id="branch-456",
            objective="Test XSS",
            summary="Branch failed: timeout",
            steps_taken=3,
            success=False,
            error="Execution timeout",
        )
        
        assert result.success is False
        assert result.error == "Execution timeout"


class TestBranchManager:
    """Tests for BranchManager class."""
    
    def test_init(self):
        """Test initializing branch manager."""
        store = ContextStore()
        manager = BranchManager(store)
        
        assert manager._store is store
    
    @pytest.mark.asyncio
    async def test_branch_and_execute(self):
        """Test branch and execute with simple executor."""
        store = ContextStore()
        manager = BranchManager(store)
        
        async def simple_executor(ctx: ContextStore, objective: str) -> str:
            return f"Completed: {objective}"
        
        results = await manager.branch_and_execute(
            objectives=["Task A", "Task B"],
            executor=simple_executor,
            max_parallel=2,
        )
        
        assert len(results) == 2
        assert all(r.success for r in results)
        assert "Task A" in [r.objective for r in results]
        assert "Task B" in [r.objective for r in results]
    
    @pytest.mark.asyncio
    async def test_branch_handles_errors(self):
        """Test that branch handles executor errors gracefully."""
        store = ContextStore()
        manager = BranchManager(store)
        
        async def failing_executor(ctx: ContextStore, objective: str) -> str:
            if "fail" in objective:
                raise ValueError("Intentional failure")
            return "Success"
        
        results = await manager.branch_and_execute(
            objectives=["succeed", "fail this"],
            executor=failing_executor,
            max_parallel=2,
        )
        
        assert len(results) == 2
        
        success_result = next(r for r in results if r.objective == "succeed")
        fail_result = next(r for r in results if r.objective == "fail this")
        
        assert success_result.success is True
        assert fail_result.success is False
        assert "Intentional failure" in fail_result.error
    
    @pytest.mark.asyncio
    async def test_concurrency_limit(self):
        """Test that max_parallel is respected."""
        store = ContextStore()
        manager = BranchManager(store)
        
        import asyncio
        concurrent_count = 0
        max_concurrent = 0
        lock = asyncio.Lock()
        
        async def tracking_executor(ctx: ContextStore, objective: str) -> str:
            nonlocal concurrent_count, max_concurrent
            async with lock:
                concurrent_count += 1
                max_concurrent = max(max_concurrent, concurrent_count)
            
            await asyncio.sleep(0.1)  # Simulate work
            
            async with lock:
                concurrent_count -= 1
            
            return "Done"
        
        results = await manager.branch_and_execute(
            objectives=["A", "B", "C", "D"],
            executor=tracking_executor,
            max_parallel=2,
        )
        
        assert len(results) == 4
        assert max_concurrent <= 2
    
    @pytest.mark.asyncio
    async def test_explore_parallel(self):
        """Test explore_parallel helper method."""
        store = ContextStore()
        manager = BranchManager(store)
        
        results = await manager.explore_parallel(
            objectives=["Explore A", "Explore B"],
            step_limit=5,
        )
        
        assert len(results) == 2
        assert all(r.success for r in results)
