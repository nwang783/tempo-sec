"""Tests for tempo/tools/meta.py."""

import pytest

from tempo.tools.meta import (
    FinishTaskTool,
    FinishSubtaskTool,
    SummarizeOutputTool,
)
from tempo.context.store import ContextStore
from tempo.context.frame import ToolCall


class TestFinishTaskTool:
    """Tests for FinishTaskTool class."""
    
    def test_name_and_category(self):
        """Test tool name and category are set."""
        tool = FinishTaskTool()
        assert tool.name == "complete_analysis"
        assert tool.category.value == "meta"
    
    def test_get_schema(self):
        """Test schema generation."""
        tool = FinishTaskTool()
        schema = tool.get_schema().to_openai_format()
        
        assert schema["function"]["name"] == "complete_analysis"
        assert "findings" in schema["function"]["parameters"]["properties"]
    
    @pytest.mark.asyncio
    async def test_execute(self):
        """Test finishing a task."""
        tool = FinishTaskTool()
        
        result = await tool.execute(
            findings="Found SQL injection vulnerability",
            purpose="Complete task",
        )
        
        assert result.success is True
        assert result.metadata["finish"] is True
        assert "SQL injection" in result.output


class TestFinishSubtaskTool:
    """Tests for FinishSubtaskTool class."""
    
    def test_name_and_category(self):
        """Test tool name and category are set."""
        tool = FinishSubtaskTool()
        assert tool.name == "finish_subtask"
        assert tool.category.value == "meta"
    
    @pytest.mark.asyncio
    async def test_execute_with_summary(self):
        """Test finishing a subtask with summary."""
        tool = FinishSubtaskTool()
        
        result = await tool.execute(
            summary="Investigated login form, no vulnerabilities found",
            purpose="Report completion",
        )
        
        assert result.success is True
        assert result.metadata["subtask_complete"] is True
        assert result.metadata["summary"] == "Investigated login form, no vulnerabilities found"
    
    @pytest.mark.asyncio
    async def test_execute_with_findings(self):
        """Test finishing a subtask with findings."""
        tool = FinishSubtaskTool()
        
        findings = [
            {"type": "xss", "description": "Reflected XSS in search", "severity": "high"},
        ]
        
        result = await tool.execute(
            summary="Found XSS vulnerability",
            findings=findings,
            purpose="Report findings",
        )
        
        assert result.success is True
        assert len(result.metadata["findings"]) == 1


class TestSummarizeOutputTool:
    """Tests for SummarizeOutputTool class."""
    
    def test_name_and_category(self):
        """Test tool name and category are set."""
        store = ContextStore()
        tool = SummarizeOutputTool(context_store=store)
        
        assert tool.name == "summarize_tool_output"
        assert tool.category.value == "meta"
    
    @pytest.mark.asyncio
    async def test_summarize_existing_tool_call(self):
        """Test summarizing an existing tool call."""
        store = ContextStore()
        
        # Add a tool call
        tc = ToolCall(tool_name="shell", raw_output="Very long output " * 100)
        store.add_tool_call(tc)
        
        tool = SummarizeOutputTool(context_store=store)
        result = await tool.execute(
            tool_call_id=tc.id,
            summary="Command executed successfully",
            purpose="Reduce context",
        )
        
        assert result.success is True
        assert tc.summary == "Command executed successfully"
    
    @pytest.mark.asyncio
    async def test_summarize_nonexistent_fails(self):
        """Test summarizing nonexistent tool call fails."""
        store = ContextStore()
        tool = SummarizeOutputTool(context_store=store)
        
        result = await tool.execute(
            tool_call_id="fake-id",
            summary="Summary",
            purpose="Test",
        )
        
        assert result.success is False
        assert "not found" in result.error.lower()
