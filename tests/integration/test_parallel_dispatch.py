"""Integration tests for parallel subagent dispatching."""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from tempo.tools.dispatch_subagent import DispatchSubagentsTool, DispatchSubagentTool, ToolResult
from tempo.findings.document import FindingsDocument
from tempo.findings.schema import Severity

class TestParallelDispatchIntegration:
    """Integration scenarios for parallel dispatching."""

    @pytest.fixture
    def findings_doc(self):
        return FindingsDocument(target="https://example.com")

    @pytest.mark.asyncio
    async def test_concurrent_findings_updates(self, findings_doc):
        """
        Integration test verifying that running multiple subagents concurrently
        safely updates the shared findings document.
        """
        # Create a tool with high concurrency
        tool = DispatchSubagentsTool(findings=findings_doc, max_concurrent=10)
        
        # We need to simulate subagents that actually take time and update findings
        # We'll monkeypatch the _run_subagent method of the internal tool to simulate this
        
        async def simulated_subagent(subagent_type, objective, focus_area, max_steps):
            # Simulate work
            await asyncio.sleep(0.01)
            
            # Extract index from objective to generate unique data
            idx = int(objective.split("#")[1])
            
            # Use async method to update findings
            await findings_doc.add_finding_async(
                finding_id=f"finding-{idx}",
                title=f"Finding {idx}",
                severity=Severity.LOW,
                status="suspected",
                description=f"Found by agent {idx}",
                evidence="proof",
                discovered_by=f"subagent-{idx}"
            )
            
            await findings_doc.add_attack_surface_async(
                surface_id=f"surface-{idx}",
                surface_type="endpoint",
                url=f"/api/{idx}",
                description="desc",
                discovered_by=f"subagent-{idx}"
            )
            
            # Return result
            return ToolResult(
                success=True,
                output="Done",
                metadata={
                    "subagent_type": subagent_type,
                    "findings_added": 1,
                    "surfaces_added": 1,
                    "steps_taken": 5,
                    "summary": f"Completed task {idx}"
                }
            )
            
        # Patch the method on the instance
        tool._single_dispatch._run_subagent = simulated_subagent
        
        # Create many requests
        count = 20
        requests = [
            {
                "subagent_type": "recon", 
                "objective": f"Task #{i}",
                "max_steps": 10
            } 
            for i in range(count)
        ]
        
        # Run them all
        result = await tool.execute(dispatch_requests=requests)
        
        # Verify success
        assert result.success is True
        assert result.metadata["total_dispatched"] == count
        assert result.metadata["successful_count"] == count
        
        # Verify findings document integrity
        assert len(findings_doc.data.findings) == count
        assert len(findings_doc.data.attack_surfaces) == count
        
        # Verify all IDs present
        finding_ids = {f.id for f in findings_doc.data.findings}
        for i in range(count):
            assert f"finding-{i}" in finding_ids

    @pytest.mark.asyncio
    async def test_concurrency_limiting(self, findings_doc):
        """Verify that max_concurrent actually limits active tasks."""
        # Set max concurrent to 2
        tool = DispatchSubagentsTool(findings=findings_doc, max_concurrent=2)
        
        active_tasks = 0
        max_seen_active = 0
        lock = asyncio.Lock()
        
        async def tracked_subagent(*args, **kwargs):
            nonlocal active_tasks, max_seen_active
            async with lock:
                active_tasks += 1
                max_seen_active = max(max_seen_active, active_tasks)
            
            # Sleep to ensure overlap
            await asyncio.sleep(0.05)
            
            async with lock:
                active_tasks -= 1
                
            return ToolResult(success=True, output="ok", metadata={})
            
        tool._single_dispatch._run_subagent = tracked_subagent
        
        requests = [{"subagent_type": "recon", "objective": "test"} for _ in range(10)]
        
        await tool.execute(dispatch_requests=requests)
        
        # Ideally, should never exceed max_concurrent + small buffer?
        # Note: asyncio.Semaphore doesn't strictly guarantee approximate count in implementation details
        # but for this test, we expect it to be close to 2.
        # Actually, since we explicitly use a Semaphore(2), it SHOULD be exactly 2.
        
        assert max_seen_active <= 2
