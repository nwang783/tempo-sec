"""Tests for tempo/tools/meta.py."""

import pytest
from unittest.mock import patch, mock_open, MagicMock
from pathlib import Path

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
            assert result.metadata["risk_level"] == level
            assert level.upper() in result.output

    @pytest.mark.asyncio
    async def test_execute_saves_report_file(self, findings_doc):
        """Test that report is saved to a file."""
        tool = FinalizeAnalysisTool(findings_updater=findings_doc)
        
        # Mock Path and open to prevent actual file system writes
        with patch("tempo.tools.meta.open", mock_open()) as m_open, \
             patch("tempo.tools.meta.Path.mkdir") as m_mkdir:
            
            result = await tool.execute(
                final_report="# Final Report\nContent here.",
                purpose="Testing save",
            )
            
            # Check success
            assert result.success is True
            assert result.metadata["finalize_complete"] is True
            assert "Report saved to" in result.output
            
            # Check directory creation - expect findings/example_com
            # (target is https://example.com in fixture -> example_com)
            m_mkdir.assert_called()
            
            # Check file write
            m_open.assert_called()
            handle = m_open()
            handle.write.assert_called()
            
            # Verify content availability in metadata
            assert "report_path" in result.metadata
            # Dot is preserved in filename
            assert "findings/example.com/report.md" in result.metadata["report_path"]
