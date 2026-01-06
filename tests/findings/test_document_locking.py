"""Tests for FindingsDocument thread-safety."""

import asyncio
import pytest
from unittest.mock import MagicMock, patch
from tempo.findings.document import FindingsDocument
from tempo.findings.schema import Severity, FindingStatus

class TestFindingsDocumentLocking:
    """Tests for FindingsDocument async locking."""

    @pytest.fixture
    def findings_doc(self):
        """Create a findings document for testing."""
        return FindingsDocument(target="https://example.com")

    @pytest.mark.asyncio
    async def test_async_lock_initialization(self, findings_doc):
        """Test that the lock is initialized correctly."""
        assert hasattr(findings_doc, "_lock")
        assert isinstance(findings_doc._lock, asyncio.Lock)
        assert not findings_doc._lock.locked()

    @pytest.mark.asyncio
    async def test_add_finding_async_acquires_lock(self, findings_doc):
        """Test that add_finding_async acquires the lock."""
        # Mock the synchronous add_finding method
        with patch.object(findings_doc, "add_finding") as mock_add_finding:
            # Create a spy on the lock's acquire method
            with patch.object(findings_doc._lock, "acquire", wraps=findings_doc._lock.acquire) as mock_acquire:
                await findings_doc.add_finding_async(
                    finding_id="test-1",
                    title="Test Finding",
                    severity=Severity.HIGH,
                    status="suspected",
                    description="Test description",
                    evidence="Test evidence",
                    discovered_by="test-agent"
                )
                
                # Check that acquire was called
                mock_acquire.assert_called()
                # Check that add_finding was called
                mock_add_finding.assert_called_once()

    @pytest.mark.asyncio
    async def test_concurrent_access(self, findings_doc):
        """Test concurrent access to findings document."""
        # Create a mock add_finding that sleeps to simulate work
        original_add_finding = findings_doc.add_finding
        
        async def slow_add_finding(*args, **kwargs):
            await asyncio.sleep(0.01)
            return original_add_finding(*args, **kwargs)
            
        # We need to monkeypatch the internal call, but since add_finding_async calls
        # self.add_finding, we can just replace add_finding with a wrapper that sleeps isn't easy 
        # because add_finding is sync.
        
        # Instead, let's verify that we can run multiple async operations without error
        tasks = []
        for i in range(10):
            tasks.append(
                findings_doc.add_finding_async(
                    finding_id=f"finding-{i}",
                    title=f"Finding {i}",
                    severity=Severity.LOW,
                    status="suspected",
                    description=f"Description {i}",
                    evidence="Evidence",
                    discovered_by="tester"
                )
            )
            
        # Run all tasks concurrently
        results = await asyncio.gather(*tasks)
        
        assert len(results) == 10
        assert len(findings_doc.data.findings) == 10
        # Verify IDs are unique and correct
        ids = {f.id for f in findings_doc.data.findings}
        assert len(ids) == 10
        assert "finding-0" in ids
        assert "finding-9" in ids

    @pytest.mark.asyncio
    async def test_mixed_async_operations(self, findings_doc):
        """Test mixing different async operations concurrently."""
        
        async def add_surface(i):
            await findings_doc.add_attack_surface_async(
                surface_id=f"surface-{i}",
                surface_type="endpoint",
                url=f"/api/{i}",
                description="Test endpoint",
                discovered_by="tester"
            )
            
        async def add_finding(i):
            await findings_doc.add_finding_async(
                finding_id=f"finding-{i}",
                title=f"Finding {i}",
                severity=Severity.MEDIUM,
                status="suspected",
                description="Desc",
                evidence="Ev",
                discovered_by="tester"
            )
            
        async def inc_steps(i):
            await findings_doc.increment_steps_async(1)
            
        tasks = []
        # Mix operations
        for i in range(5):
            tasks.append(add_surface(i))
            tasks.append(add_finding(i))
            tasks.append(inc_steps(i))
            
        await asyncio.gather(*tasks)
        
        assert len(findings_doc.data.attack_surfaces) == 5
        assert len(findings_doc.data.findings) == 5
        assert findings_doc.data.total_steps_taken == 5

    @pytest.mark.asyncio
    async def test_save_async_locking(self, findings_doc):
        """Test that save_async uses the lock."""
        with patch.object(findings_doc, "save") as mock_save:
            with patch.object(findings_doc._lock, "acquire", wraps=findings_doc._lock.acquire) as mock_acquire:
                await findings_doc.save_async("test.yaml")
                
                mock_acquire.assert_called()
                mock_save.assert_called_with("test.yaml")
