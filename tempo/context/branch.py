"""
Branch manager for parallel exploration.

Handles the logic for branching, parallel execution, and merging
of exploration paths.
"""

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from tempo.context.store import ContextStore


@dataclass
class BranchResult:
    """Result from executing a branch."""
    branch_id: str
    objective: str
    summary: str
    steps_taken: int
    success: bool
    error: str | None = None


class BranchManager:
    """
    Handles the logic for branching, parallel execution, and merging.
    Works with ContextStore but encapsulates branching complexity.
    """
    
    def __init__(self, context_store: ContextStore):
        """
        Initialize the branch manager.
        
        Args:
            context_store: The context store to manage branches for
        """
        self._store = context_store
    
    async def branch_and_execute(
        self,
        objectives: list[str],
        executor: Callable[[ContextStore, str], Awaitable[str]],
        max_parallel: int = 3,
    ) -> list[BranchResult]:
        """
        Create branches, execute each with the given executor, collect results.
        
        Args:
            objectives: List of objectives, one per branch
            executor: Async function that takes (context_store, objective) and returns summary
            max_parallel: Maximum concurrent branches
            
        Returns:
            List of BranchResult with summaries and metadata
        """
        # Create branches
        branch_ids = self._store.branch(len(objectives), objectives)
        
        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_parallel)
        
        async def execute_branch(branch_id: str, objective: str) -> BranchResult:
            """Execute a single branch with semaphore control."""
            async with semaphore:
                # Switch to branch
                self._store.switch_to_branch(branch_id)
                
                steps = 0
                try:
                    # Execute the branch
                    summary = await executor(self._store, objective)
                    
                    # Count steps (tool calls in this branch)
                    frame = self._store.current_frame
                    steps = len(frame.tool_calls)
                    
                    return BranchResult(
                        branch_id=branch_id,
                        objective=objective,
                        summary=summary,
                        steps_taken=steps,
                        success=True,
                    )
                except Exception as e:
                    return BranchResult(
                        branch_id=branch_id,
                        objective=objective,
                        summary=f"Branch failed: {str(e)}",
                        steps_taken=steps,
                        success=False,
                        error=str(e),
                    )
        
        # Execute all branches concurrently
        tasks = [
            execute_branch(bid, obj)
            for bid, obj in zip(branch_ids, objectives)
        ]
        results = await asyncio.gather(*tasks)
        
        # Merge results back
        summaries = [r.summary for r in results]
        self._store.merge_branches(branch_ids, summaries)
        
        return list(results)
    
    async def explore_parallel(
        self,
        objectives: list[str],
        step_limit: int = 10,
    ) -> list[BranchResult]:
        """
        Explore multiple objectives in parallel with a step limit.
        
        This is a simplified version that uses a basic executor.
        
        Args:
            objectives: Objectives to explore
            step_limit: Maximum steps per branch
            
        Returns:
            List of BranchResult
        """
        async def simple_executor(store: ContextStore, objective: str) -> str:
            """Simple executor that just records the objective."""
            store.add_message(
                role=store.current_frame.messages[0].role if store.current_frame.messages else "user",
                content=f"Exploring: {objective}",
            )
            return f"Completed exploration of: {objective}"
        
        return await self.branch_and_execute(
            objectives=objectives,
            executor=simple_executor,
            max_parallel=len(objectives),
        )
