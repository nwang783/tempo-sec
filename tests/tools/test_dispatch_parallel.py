"""Tests for DispatchSubagentTool parallel dispatch mode."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from tempo.tools.dispatch_subagents import DispatchSubagentsTool, ToolResult
from tempo.findings.document import FindingsDocument
from tempo.tools.base import ToolCategory

class TestDispatchSubagentToolParallel:
    """Tests for DispatchSubagentTool parallel dispatch functionality."""

    @pytest.fixture
    def findings_doc(self):
        """Create a findings document for testing."""
        return FindingsDocument(target="https://example.com")

    @pytest.fixture
    def tool(self, findings_doc):
        """Create the tool instance."""
        return DispatchSubagentsTool(findings=findings_doc, max_concurrent=2)

    def test_tool_properties(self, tool):
        """Test tool properties."""
        assert tool.name == "dispatch_subagents"
        assert tool.category == ToolCategory.META
        assert tool._max_concurrent == 2
        assert "parallel" in tool.description.lower()

    @pytest.mark.asyncio
    async def test_execute_empty_requests(self, tool):
        """Test execution with empty requests list."""
        result = await tool.execute(dispatch_requests=[])
        assert result.success is False
        assert "non-empty list" in result.error

    @pytest.mark.asyncio
    async def test_execute_invalid_requests(self, tool):
        """Test execution with malformed requests."""
        # Not a dict
        result = await tool.execute(dispatch_requests=["not-a-dict"])
        assert result.success is False
        assert "not a dictionary" in result.error

        # Missing objective
        result = await tool.execute(dispatch_requests=[{"subagent_type": "recon"}])
        assert result.success is False
        assert "missing required 'objective'" in result.error

        # Invalid type
        result = await tool.execute(dispatch_requests=[
            {"subagent_type": "invalid", "objective": "test"}
        ])
        assert result.success is False
        assert "invalid subagent_type" in result.error

    @pytest.mark.asyncio
    async def test_execute_parallel_success(self, tool):
        """Test successful parallel execution."""
        # Mock the single dispatch execution
        mock_result_1 = ToolResult(
            success=True, 
            output="Subagent 1 done",
            metadata={
                "subagent_id": "id-1",
                "subagent_type": "recon",
                "summary": "Found things",
                "surfaces_added": 2,
                "findings_added": 0,
                "steps_taken": 5
            }
        )
        mock_result_2 = ToolResult(
            success=True,
            output="Subagent 2 done",
            metadata={
                "subagent_id": "id-2",
                "subagent_type": "test",
                "summary": "Tested things",
                "surfaces_added": 0,
                "findings_added": 1,
                "steps_taken": 10
            }
        )
        
        # Mock _run_subagent on the tool directly
        tool._run_subagent = AsyncMock(side_effect=[mock_result_1, mock_result_2])

        requests = [
            {"subagent_type": "recon", "objective": "Recon task"},
            {"subagent_type": "test", "objective": "Test task"}
        ]
        
        result = await tool.execute(dispatch_requests=requests)
        
        assert result.success is True
        assert "Total subagents dispatched:** 2" in result.output
        assert "Successful:** 2" in result.output
        assert "Total attack surfaces added:** 2" in result.output
        assert "Total findings added:** 1" in result.output
        
        # Check metadata aggregation
        assert result.metadata["total_dispatched"] == 2
        assert result.metadata["successful_count"] == 2
        assert result.metadata["total_surfaces_added"] == 2
        assert result.metadata["total_findings_added"] == 1
        
        # Verify calls
        assert tool._run_subagent.call_count == 2

    @pytest.mark.asyncio
    async def test_execute_parallel_partial_failure(self, tool):
        """Test parallel execution with some failures."""
        mock_result_success = ToolResult(
            success=True,
            output="Success",
            metadata={"summary": "OK", "steps_taken": 5}
        )
        mock_result_failure = ToolResult(
            success=False,
            output="Failed",
            error="Something broke",
            metadata={"steps_taken": 2}
        )
        
        tool._run_subagent = AsyncMock(side_effect=[mock_result_success, mock_result_failure])
        
        requests = [
            {"subagent_type": "recon", "objective": "Task 1"},
            {"subagent_type": "test", "objective": "Task 2"}
        ]
        
        result = await tool.execute(dispatch_requests=requests)
        
        # Overall success is False if any subagent failed
        assert result.success is False
        assert "1 subagent(s) failed" in result.error
        
        assert "Successful:** 1" in result.output
        assert "Failed:** 1" in result.output
        assert "Something broke" in result.output

    def test_get_schema_includes_parallel_option(self, tool):
        """Test schema includes dispatch_requests for parallel dispatch."""
        schema = tool.get_schema()
        assert schema.name == "dispatch_subagents"
        
        props = schema.parameters["properties"]
        # Single dispatch params
        assert "subagent_type" in props
        assert "objective" in props
        assert "focus_area" in props
        # Parallel dispatch param
        assert "dispatch_requests" in props
        assert props["dispatch_requests"]["type"] == "array"
        
        item_props = props["dispatch_requests"]["items"]["properties"]
        assert "subagent_type" in item_props
        assert "objective" in item_props
        assert "focus_area" in item_props
        assert "scope" in item_props

    @pytest.mark.asyncio
    async def test_single_dispatch_still_works(self, tool):
        """Test that single dispatch mode still works."""
        mock_result = ToolResult(
            success=True,
            output="Single subagent done",
            metadata={"subagent_id": "id-1", "subagent_type": "recon"}
        )
        tool._run_subagent = AsyncMock(return_value=mock_result)
        
        result = await tool.execute(
            subagent_type="recon",
            objective="Single recon task"
        )
        
        assert result.success is True
        tool._run_subagent.assert_called_once()

    @pytest.mark.asyncio
    async def test_requires_either_mode(self, tool):
        """Test that either single dispatch params or dispatch_requests is required."""
        result = await tool.execute()
        assert result.success is False
        assert "subagent_type is required" in result.error
