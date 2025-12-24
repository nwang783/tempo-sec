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
        assert "Analysis complete" in result.output
    
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


class TestCreateTestPlanTool:
    """Tests for CreateTestPlanTool class."""
    
    def test_name_and_category(self):
        """Test tool name and category are set."""
        store = ContextStore()
        from tempo.tools.meta import CreateTestPlanTool
        tool = CreateTestPlanTool(test_plan_manager=store)
        
        assert tool.name == "create_test_plan"
        assert tool.category.value == "meta"
    
    @pytest.mark.asyncio
    async def test_create_plan_adds_items_to_state(self):
        """Test that creating a plan populates test_plan in state."""
        store = ContextStore()
        from tempo.tools.meta import CreateTestPlanTool
        tool = CreateTestPlanTool(test_plan_manager=store)
        
        result = await tool.execute(
            items=[
                {"description": "Test auth bypass", "priority": "high"},
                {"description": "Check input validation", "priority": "medium"},
            ],
            purpose="Create initial plan",
        )
        
        assert result.success is True
        assert result.metadata["plan_created"] is True
        assert result.metadata["item_count"] == 2
        
        # Check items were added to state
        plan = store.get_test_plan()
        assert len(plan) == 2
        assert plan[0]["description"] == "Test auth bypass"
        assert plan[0]["priority"] == "high"
        assert plan[0]["status"] == "pending"
        assert plan[1]["priority"] == "medium"
    
    @pytest.mark.asyncio
    async def test_create_plan_requires_items(self):
        """Test that empty items list fails."""
        store = ContextStore()
        from tempo.tools.meta import CreateTestPlanTool
        tool = CreateTestPlanTool(test_plan_manager=store)
        
        result = await tool.execute(items=[], purpose="Test")
        
        assert result.success is False
        assert "at least one item" in result.error.lower()


class TestAddTodoTool:
    """Tests for AddTodoTool class."""
    
    def test_name_and_category(self):
        """Test tool name and category are set."""
        store = ContextStore()
        from tempo.tools.meta import AddTodoTool
        tool = AddTodoTool(test_plan_manager=store)
        
        assert tool.name == "add_todo"
        assert tool.category.value == "meta"
    
    @pytest.mark.asyncio
    async def test_add_todo_creates_item(self):
        """Test that adding a todo creates an item in state."""
        store = ContextStore()
        from tempo.tools.meta import AddTodoTool
        tool = AddTodoTool(test_plan_manager=store)
        
        result = await tool.execute(
            description="New investigation area",
            priority="high",
            purpose="Add followup",
        )
        
        assert result.success is True
        assert "item_id" in result.metadata
        
        plan = store.get_test_plan()
        assert len(plan) == 1
        assert plan[0]["description"] == "New investigation area"
        assert plan[0]["priority"] == "high"
    
    @pytest.mark.asyncio
    async def test_add_todo_defaults_to_medium_priority(self):
        """Test that priority defaults to medium."""
        store = ContextStore()
        from tempo.tools.meta import AddTodoTool
        tool = AddTodoTool(test_plan_manager=store)
        
        await tool.execute(description="Test item", purpose="Test")
        
        plan = store.get_test_plan()
        assert plan[0]["priority"] == "medium"


class TestCompleteTodoTool:
    """Tests for CompleteTodoTool class."""
    
    def test_name_and_category(self):
        """Test tool name and category are set."""
        store = ContextStore()
        from tempo.tools.meta import CompleteTodoTool
        tool = CompleteTodoTool(test_plan_manager=store)
        
        assert tool.name == "complete_todo"
        assert tool.category.value == "meta"
    
    @pytest.mark.asyncio
    async def test_complete_todo_updates_status(self):
        """Test that completing a todo updates its status."""
        store = ContextStore()
        from tempo.tools.meta import AddTodoTool, CompleteTodoTool
        
        # Add an item first
        add_tool = AddTodoTool(test_plan_manager=store)
        add_result = await add_tool.execute(description="Test item", purpose="Setup")
        item_id = add_result.metadata["item_id"]
        
        # Complete it
        complete_tool = CompleteTodoTool(test_plan_manager=store)
        result = await complete_tool.execute(
            item_id=item_id,
            status="completed",
            reason="Found SQL injection vulnerability",
            purpose="Mark done",
        )
        
        assert result.success is True
        
        plan = store.get_test_plan()
        assert plan[0]["status"] == "completed"
        assert plan[0]["reason"] == "Found SQL injection vulnerability"
        assert plan[0]["completed_at"] is not None
    
    @pytest.mark.asyncio
    async def test_complete_todo_requires_reason(self):
        """Test that completing without reason fails."""
        store = ContextStore()
        from tempo.tools.meta import AddTodoTool, CompleteTodoTool
        
        add_tool = AddTodoTool(test_plan_manager=store)
        add_result = await add_tool.execute(description="Test item", purpose="Setup")
        item_id = add_result.metadata["item_id"]
        
        complete_tool = CompleteTodoTool(test_plan_manager=store)
        result = await complete_tool.execute(
            item_id=item_id,
            status="completed",
            reason="",
            purpose="Test",
        )
        
        assert result.success is False
        assert "reason is required" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_complete_todo_invalid_id_fails(self):
        """Test that completing nonexistent item fails."""
        store = ContextStore()
        from tempo.tools.meta import CompleteTodoTool
        tool = CompleteTodoTool(test_plan_manager=store)
        
        result = await tool.execute(
            item_id="fake-id",
            status="completed",
            reason="Some reason",
            purpose="Test",
        )
        
        assert result.success is False
        assert "not found" in result.error.lower()
