"""
Branch coordinator for agent-initiated parallel exploration.

Manages subagent lifecycle and result merging when the agent
calls branch_to_subtasks.
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from tempo.context.store import ContextStore
from tempo.context.frame import MessageRole


@dataclass
class SubtaskResult:
    """Result from a completed subtask."""
    subtask_id: str
    objective: str
    summary: str
    findings: list[dict] = field(default_factory=list)
    success: bool = True
    error: str | None = None


@dataclass
class PendingBranch:
    """Tracks a pending branch operation."""
    branch_id: str
    parent_frame_id: str
    subtasks: list[str]
    context_branch_ids: list[str]  # Frame IDs for each subtask
    results: dict[str, SubtaskResult] = field(default_factory=dict)
    complete_event: asyncio.Event = field(default_factory=asyncio.Event)


class BranchCoordinator:
    """
    Coordinates agent-initiated branching.
    
    When the agent calls branch_to_subtasks:
    1. Creates branch frames in ContextStore
    2. Spawns subagent runs (clones with subtask objectives)
    3. Collects results as subagents call finish_subtask
    4. Merges summaries into a single message for main agent
    """
    
    def __init__(
        self,
        context_store: ContextStore,
        agent_factory: Callable[[ContextStore, str], Awaitable[SubtaskResult]] | None = None,
    ):
        """
        Initialize the branch coordinator.
        
        Args:
            context_store: Context store for creating branches
            agent_factory: Factory function to create subagent instances.
                           Takes (context_store, objective) and returns SubtaskResult.
        """
        self.context = context_store
        self.agent_factory = agent_factory
        self._pending_branches: dict[str, PendingBranch] = {}
    
    async def spawn_subtasks(self, subtasks: list[str]) -> str:
        """
        Spawn subagents for each subtask.
        
        Args:
            subtasks: List of subtask objectives
            
        Returns:
            branch_id that can be used to track completion
        """
        branch_id = str(uuid.uuid4())
        parent_frame_id = self.context.current_frame.id
        
        # Create branches in context store
        context_branch_ids = self.context.branch(len(subtasks), subtasks)
        
        # Create pending branch tracker
        pending = PendingBranch(
            branch_id=branch_id,
            parent_frame_id=parent_frame_id,
            subtasks=subtasks,
            context_branch_ids=context_branch_ids,
        )
        self._pending_branches[branch_id] = pending
        
        # If we have an agent factory, spawn the subagents
        if self.agent_factory:
            asyncio.create_task(self._run_subagents(pending))
        
        return branch_id
    
    async def _run_subagents(self, pending: PendingBranch) -> None:
        """Execute subagents in parallel."""
        async def run_one(subtask_idx: int) -> SubtaskResult:
            subtask = pending.subtasks[subtask_idx]
            branch_frame_id = pending.context_branch_ids[subtask_idx]
            
            try:
                # Switch to branch context
                self.context.switch_to_branch(branch_frame_id)
                
                # Run the subagent
                result = await self.agent_factory(self.context, subtask)
                return result
            except Exception as e:
                return SubtaskResult(
                    subtask_id=branch_frame_id,
                    objective=subtask,
                    summary=f"Subtask failed: {str(e)}",
                    success=False,
                    error=str(e),
                )
        
        # Run all subtasks in parallel
        tasks = [run_one(i) for i in range(len(pending.subtasks))]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Collect results
        for i, result in enumerate(results):
            subtask_id = pending.context_branch_ids[i]
            if isinstance(result, Exception):
                pending.results[subtask_id] = SubtaskResult(
                    subtask_id=subtask_id,
                    objective=pending.subtasks[i],
                    summary=f"Subtask failed: {str(result)}",
                    success=False,
                    error=str(result),
                )
            else:
                result.subtask_id = subtask_id
                pending.results[subtask_id] = result
        
        # Signal completion
        pending.complete_event.set()
    
    def record_subtask_result(
        self,
        branch_id: str,
        subtask_id: str,
        summary: str,
        findings: list[dict] | None = None,
        success: bool = True,
        error: str | None = None,
    ) -> bool:
        """
        Record a subtask completion (called when subagent calls finish_subtask).
        
        Args:
            branch_id: Branch operation ID
            subtask_id: Specific subtask ID
            summary: Subtask summary
            findings: Optional findings
            success: Whether subtask succeeded
            error: Error message if failed
            
        Returns:
            True if all subtasks are now complete
        """
        if branch_id not in self._pending_branches:
            return False
        
        pending = self._pending_branches[branch_id]
        
        # Find the objective for this subtask
        try:
            idx = pending.context_branch_ids.index(subtask_id)
            objective = pending.subtasks[idx]
        except ValueError:
            objective = "Unknown"
        
        pending.results[subtask_id] = SubtaskResult(
            subtask_id=subtask_id,
            objective=objective,
            summary=summary,
            findings=findings or [],
            success=success,
            error=error,
        )
        
        # Check if all complete
        all_complete = len(pending.results) == len(pending.subtasks)
        if all_complete:
            pending.complete_event.set()
        
        return all_complete
    
    async def await_completion(self, branch_id: str, timeout: float | None = None) -> list[SubtaskResult]:
        """
        Wait for all subtasks in a branch to complete.
        
        Args:
            branch_id: Branch operation ID
            timeout: Optional timeout in seconds
            
        Returns:
            List of SubtaskResult for each subtask
        """
        if branch_id not in self._pending_branches:
            return []
        
        pending = self._pending_branches[branch_id]
        
        try:
            await asyncio.wait_for(pending.complete_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass
        
        return list(pending.results.values())
    
    def merge_results(self, results: list[SubtaskResult]) -> str:
        """
        Merge subtask results into a single summary message.
        
        Args:
            results: List of subtask results
            
        Returns:
            Merged summary string
        """
        if not results:
            return "No subtask results."
        
        parts = []
        all_findings = []
        
        for r in results:
            status = "✓" if r.success else "✗"
            parts.append(f"## {status} Subtask: {r.objective}")
            parts.append(r.summary)
            
            if r.findings:
                all_findings.extend(r.findings)
            
            if r.error:
                parts.append(f"Error: {r.error}")
            
            parts.append("")
        
        merged = "\n".join(parts)
        
        if all_findings:
            merged += f"\n### Combined Findings ({len(all_findings)} total)\n"
            for f in all_findings:
                severity = f.get("severity", "unknown")
                desc = f.get("description", "No description")
                merged += f"- [{severity}] {desc}\n"
        
        return merged
    
    def finalize_branch(self, branch_id: str) -> str:
        """
        Finalize a branch operation and merge results into main context.
        
        Args:
            branch_id: Branch operation ID
            
        Returns:
            Merged summary message
        """
        if branch_id not in self._pending_branches:
            return "Branch not found."
        
        pending = self._pending_branches[branch_id]
        results = list(pending.results.values())
        
        # Merge results
        merged_summary = self.merge_results(results)
        
        # Merge branches in context store
        summaries = [r.summary for r in results]
        self.context.merge_branches(pending.context_branch_ids, summaries)
        
        # Clean up
        del self._pending_branches[branch_id]
        
        return merged_summary
    
    def is_complete(self, branch_id: str) -> bool:
        """Check if all subtasks in a branch are complete."""
        if branch_id not in self._pending_branches:
            return True  # Not found = complete
        
        pending = self._pending_branches[branch_id]
        return len(pending.results) == len(pending.subtasks)
