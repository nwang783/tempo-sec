"""Tests for tempo/tools/meta.py."""

import pytest

from tempo.tools.meta import (
    ContinueAnalysisTool,
    FinishTaskTool,
    FinishSubtaskTool,
    SummarizeOutputTool,
)
from tempo.context.store import ContextStore
from tempo.context.frame import ToolCall


class TestContinueAnalysisTool:
    """Tests for ContinueAnalysisTool class."""
    
    def test_name_and_category(self):
        """Test tool name and category are set."""
        tool = ContinueAnalysisTool()
        assert tool.name == "continue_analysis"
        assert tool.category.value == "meta"
    
    def test_get_schema(self):
        """Test schema generation."""
        tool = ContinueAnalysisTool()
        schema = tool.get_schema().to_openai_format()
        
        assert schema["function"]["name"] == "continue_analysis"
        assert "should_continue" in schema["function"]["parameters"]["properties"]
        assert "reasoning" in schema["function"]["parameters"]["properties"]
        assert "findings" in schema["function"]["parameters"]["properties"]
    
    @pytest.mark.asyncio
    async def test_execute_continue(self):
        """Test continuing analysis."""
        tool = ContinueAnalysisTool()
        
        result = await tool.execute(
            should_continue=True,
            reasoning="More endpoints to investigate",
        )
        
        assert result.success is True
        assert result.metadata["continue"] is True
        assert "Continuing" in result.output
    
    @pytest.mark.asyncio
    async def test_execute_finish(self):
        """Test finishing analysis with findings."""
        tool = ContinueAnalysisTool()
        
        result = await tool.execute(
            should_continue=False,
            reasoning="All phases complete",
            findings="Found SQL injection vulnerability",
        )
        
        assert result.success is True
        assert result.metadata["finish"] is True
        assert "SQL injection" in result.output
    
    @pytest.mark.asyncio
    async def test_execute_finish_requires_findings(self):
        """Test that finishing requires findings."""
        tool = ContinueAnalysisTool()
        
        result = await tool.execute(
            should_continue=False,
            reasoning="Done",
            findings="",  # Empty findings
        )
        
        assert result.success is False
        assert "must provide findings" in result.error


class TestFinishTaskToolAlias:
    """Tests for FinishTaskTool backward compatibility alias."""
    
    def test_alias_exists(self):
        """Test that FinishTaskTool is an alias for ContinueAnalysisTool."""
        assert FinishTaskTool is ContinueAnalysisTool


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
