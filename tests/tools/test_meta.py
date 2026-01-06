"""Tests for tempo/tools/meta.py."""

import pytest

from tempo.tools.meta import (
    FinishSubtaskTool,
    SummarizeOutputTool,
    FinalizeAnalysisTool,
)
from tempo.context.store import ContextStore
from tempo.context.frame import ToolCall
from tempo.findings.document import FindingsDocument


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
        
        assert tool.name == "summarize_previous_tool_output"
        assert tool.category.value == "meta"
    
    @pytest.mark.asyncio
    async def test_summarize_no_pending_fails(self):
        """Test summarizing when no output is pending fails."""
        store = ContextStore()
        tool = SummarizeOutputTool(context_store=store)
        
        result = await tool.execute(purpose="Test")
        
        assert result.success is False
        assert "no tool output pending" in result.error.lower()



class TestCreateTestPlanTool:
    """Tests for CreateTestPlanTool class."""
    
    def test_name_and_category(self):
        """Test tool name and category are set."""
        store = ContextStore()
        from tempo.tools.testplan_tools import CreateTestPlanTool
        tool = CreateTestPlanTool(test_plan_manager=store)
        
        assert tool.name == "create_test_plan"
        assert tool.category.value == "meta"
    
    @pytest.mark.asyncio
    async def test_create_plan_adds_items_to_state(self):
        """Test that creating a plan populates test_plan in state."""
        store = ContextStore()
        from tempo.tools.testplan_tools import CreateTestPlanTool
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
        from tempo.tools.testplan_tools import CreateTestPlanTool
        tool = CreateTestPlanTool(test_plan_manager=store)
        
        result = await tool.execute(items=[], purpose="Test")
        
        assert result.success is False
        assert "at least one item" in result.error.lower()


class TestAddTodoTool:
    """Tests for AddTodoTool class."""
    
    def test_name_and_category(self):
        """Test tool name and category are set."""
        store = ContextStore()
        from tempo.tools.testplan_tools import AddTodoTool
        tool = AddTodoTool(test_plan_manager=store)
        
        assert tool.name == "add_todo"
        assert tool.category.value == "meta"
    
    @pytest.mark.asyncio
    async def test_add_todo_creates_item(self):
        """Test that adding a todo creates an item in state."""
        store = ContextStore()
        from tempo.tools.testplan_tools import AddTodoTool
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
        from tempo.tools.testplan_tools import AddTodoTool
        tool = AddTodoTool(test_plan_manager=store)
        
        await tool.execute(description="Test item", purpose="Test")
        
        plan = store.get_test_plan()
        assert plan[0]["priority"] == "medium"


class TestCompleteTodoTool:
    """Tests for CompleteTodoTool class."""
    
    def test_name_and_category(self):
        """Test tool name and category are set."""
        store = ContextStore()
        from tempo.tools.testplan_tools import CompleteTodoTool
        tool = CompleteTodoTool(test_plan_manager=store)
        
        assert tool.name == "complete_todo"
        assert tool.category.value == "meta"
    
    @pytest.mark.asyncio
    async def test_complete_todo_updates_status(self):
        """Test that completing a todo updates its status."""
        store = ContextStore()
        from tempo.tools.testplan_tools import AddTodoTool, CompleteTodoTool
        
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
        from tempo.tools.testplan_tools import AddTodoTool, CompleteTodoTool
        
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
        from tempo.tools.testplan_tools import CompleteTodoTool
        tool = CompleteTodoTool(test_plan_manager=store)
        
        result = await tool.execute(
            item_id="fake-id",
            status="completed",
            reason="Some reason",
            purpose="Test",
        )
        
        assert result.success is False
        assert "not found" in result.error.lower()


class TestFinalizeAnalysisTool:
    """Tests for FinalizeAnalysisTool class."""

    @pytest.fixture
    def findings_doc(self):
        """Create a findings document for testing."""
        return FindingsDocument(target="https://example.com")

    def test_name_and_category(self, findings_doc):
        """Test tool name and category are set."""
        tool = FinalizeAnalysisTool(findings_updater=findings_doc)
        assert tool.name == "finalize_analysis"
        assert tool.category.value == "meta"

    def test_get_schema(self, findings_doc):
        """Test schema generation."""
        tool = FinalizeAnalysisTool(findings_updater=findings_doc)
        schema = tool.get_schema().to_openai_format()

        assert schema["function"]["name"] == "finalize_analysis"
        assert "final_report" in schema["function"]["parameters"]["properties"]
        assert "executive_summary" in schema["function"]["parameters"]["properties"]
        assert "risk_level" in schema["function"]["parameters"]["properties"]
        assert "final_report" in schema["function"]["parameters"]["required"]

    @pytest.mark.asyncio
    async def test_execute_basic(self, findings_doc):
        """Test basic finalize analysis execution."""
        tool = FinalizeAnalysisTool(findings_updater=findings_doc)

        result = await tool.execute(
            final_report="Comprehensive security analysis completed. No critical issues found.",
            purpose="Complete the analysis",
        )

        assert result.success is True
        assert result.metadata["finalize_complete"] is True
        assert "Analysis Complete" in result.output
        assert "security analysis completed" in result.output

    @pytest.mark.asyncio
    async def test_execute_with_all_fields(self, findings_doc):
        """Test finalize with all optional fields."""
        tool = FinalizeAnalysisTool(findings_updater=findings_doc)

        result = await tool.execute(
            final_report="Full report with all findings detailed.",
            executive_summary="Brief overview: Low risk target.",
            risk_level="high",
            purpose="Complete the analysis",
        )

        assert result.success is True
        assert result.metadata["finalize_complete"] is True
        assert result.metadata["risk_level"] == "high"
        assert result.metadata["executive_summary"] == "Brief overview: Low risk target."
        assert result.metadata["final_report"] == "Full report with all findings detailed."
        assert "HIGH" in result.output
        assert "Executive Summary" in result.output

    @pytest.mark.asyncio
    async def test_execute_invalid_risk_level_defaults_to_medium(self, findings_doc):
        """Test that invalid risk level defaults to medium."""
        tool = FinalizeAnalysisTool(findings_updater=findings_doc)

        result = await tool.execute(
            final_report="Report content",
            risk_level="invalid_level",
        )

        assert result.success is True
        assert result.metadata["risk_level"] == "medium"

    @pytest.mark.asyncio
    async def test_execute_includes_findings_summary(self, findings_doc):
        """Test that output includes findings summary."""
        # Add some findings
        findings_doc.add_attack_surface(
            surface_id="test-1",
            surface_type="endpoint",
            url="https://example.com/api",
            description="API endpoint",
            discovered_by="test",
        )
        findings_doc.add_finding(
            finding_id="finding-1",
            title="Test XSS",
            severity="high",
            status="confirmed",
            description="XSS in search",
            evidence="<script>alert(1)</script>",
            discovered_by="test",
        )

        tool = FinalizeAnalysisTool(findings_updater=findings_doc)

        result = await tool.execute(
            final_report="Analysis complete.",
        )

        assert result.success is True
        assert "Findings Summary" in result.output
        assert "Total attack surfaces: 1" in result.output
        assert "Total findings: 1" in result.output

    @pytest.mark.asyncio
    async def test_execute_risk_levels(self, findings_doc):
        """Test all valid risk levels."""
        tool = FinalizeAnalysisTool(findings_updater=findings_doc)

        for level in ["low", "medium", "high", "critical"]:
            result = await tool.execute(
                final_report=f"Report for {level} risk",
                risk_level=level,
            )

            assert result.success is True
            assert result.metadata["risk_level"] == level
            assert level.upper() in result.output
