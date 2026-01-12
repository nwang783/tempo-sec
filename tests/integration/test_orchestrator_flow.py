"""Integration tests for orchestrator flow."""

import tempfile
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from tempo.findings.document import FindingsDocument
from tempo.agents.orchestrator import OrchestratorAgent
from tempo.tools.meta import FinalizeAnalysisTool
from tempo.tools.dispatch_subagents import DispatchSubagentsTool
from tempo.agent.step_handler import StepHandler, SpecialToolResult
from tempo.context.frame import ToolCall
from tempo.context.store import ContextStore
from tempo.prompts.builder import PromptBuilder


class TestOrchestratorFlowIntegration:
    """Integration tests for orchestrator workflow."""

    @pytest.fixture
    def temp_findings_path(self):
        """Create a temporary findings file path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "test_findings.yaml"

    @pytest.fixture
    def findings_doc(self, temp_findings_path):
        """Create a findings document for testing."""
        doc = FindingsDocument(
            target="https://example.com",
            file_path=str(temp_findings_path),
        )
        return doc

    def test_finalize_analysis_integration_with_step_handler(self):
        """Test that finalize_analysis is properly handled by step handler."""
        from tempo.tools.registry import ToolRegistry

        tools = ToolRegistry()
        handler = StepHandler(tools)

        # Simulate a finalize_analysis tool call
        tool_call = ToolCall(
            id="finalize-123",
            tool_name="finalize_analysis",
            input={
                "final_report": "Comprehensive analysis complete",
                "risk_level": "high",
            },
            metadata={
                "finalize_complete": True,
                "risk_level": "high",
                "executive_summary": "",
                "final_report": "Comprehensive analysis complete",
            },
        )

        result = handler.process_special_tool(tool_call)

        assert result is not None
        assert isinstance(result, SpecialToolResult)
        assert result.tool_name == "finalize_analysis"
        assert result.should_continue is False
        assert result.findings is not None
        assert result.findings["risk_level"] == "high"
        assert result.findings["final_report"] == "Comprehensive analysis complete"

    def test_orchestrator_tools_include_dispatch_subagents(self, temp_findings_path):
        """Test that OrchestratorAgent has dispatch_subagents tool."""
        agent = OrchestratorAgent(
            target="https://example.com",
            findings_path=str(temp_findings_path),
        )
        context = ContextStore()

        tools = agent.create_tools(context=context)
        tool_names = tools.list_tools()

        assert "dispatch_subagents" in tool_names
        assert "finalize_analysis" in tool_names
        assert "read_findings" in tool_names
        assert "add_finding" in tool_names
        assert "add_attack_surface" in tool_names

    def test_orchestrator_creates_findings_on_first_access(self, temp_findings_path):
        """Test that orchestrator creates findings document on first access."""
        agent = OrchestratorAgent(
            target="https://test-target.com",
            findings_path=str(temp_findings_path),
        )

        # Accessing findings should create the document
        findings = agent.findings

        assert findings is not None
        assert findings._data.target == "https://test-target.com"

    def test_orchestrator_shares_findings_with_tools(self, temp_findings_path):
        """Test that orchestrator's tools share the findings document."""
        agent = OrchestratorAgent(
            target="https://example.com",
            findings_path=str(temp_findings_path),
        )
        context = ContextStore()

        tools = agent.create_tools(context=context)

        # Get dispatch tool and verify it has the same findings
        dispatch_tool = tools.get("dispatch_subagents")
        assert dispatch_tool is not None
        assert dispatch_tool._findings == agent.findings

        # Get read_findings tool and verify it has the same findings
        read_tool = tools.get("read_findings")
        assert read_tool is not None
        assert read_tool.findings == agent.findings

    @pytest.mark.asyncio
    async def test_finalize_analysis_execution(self, findings_doc):
        """Test finalize_analysis tool execution."""
        tool = FinalizeAnalysisTool(findings_updater=findings_doc)

        result = await tool.execute(
            final_report="Security assessment completed. 2 vulnerabilities found.",
            executive_summary="Target has moderate security posture.",
            risk_level="medium",
        )

        assert result.success is True
        assert result.metadata["finalize_complete"] is True
        assert result.metadata["risk_level"] == "medium"

    @pytest.mark.asyncio
    async def test_dispatch_then_finalize_flow(self, findings_doc):
        """Test dispatch recon followed by finalize analysis."""
        # First, simulate a recon subagent that added surfaces
        findings_doc.add_attack_surface(
            surface_id="surface-1",
            surface_type="endpoint",
            url="https://example.com/api/v1/users",
            description="User API endpoint",
            discovered_by="recon_subagent",
        )
        findings_doc.add_attack_surface(
            surface_id="surface-2",
            surface_type="form",
            url="https://example.com/login",
            description="Login form",
            discovered_by="recon_subagent",
        )

        # Then simulate a test subagent that found a vulnerability
        findings_doc.add_finding(
            finding_id="finding-1",
            title="SQL Injection in Login",
            severity="high",
            status="confirmed",
            description="SQL injection in login form",
            evidence="Error message reveals SQL syntax",
            discovered_by="test_subagent",
            attack_surface_id="surface-2",
        )
        findings_doc.mark_surface_tested("surface-1")
        findings_doc.mark_surface_tested("surface-2")

        # Now finalize
        finalize_tool = FinalizeAnalysisTool(findings_updater=findings_doc)
        result = await finalize_tool.execute(
            final_report="Discovered 2 attack surfaces and 1 high-severity vulnerability.",
            executive_summary="Critical SQL injection vulnerability requires immediate attention.",
            risk_level="high",
        )

        assert result.success is True
        assert "2 attack surfaces" in result.output or "Total attack surfaces: 2" in result.output
        assert "1" in result.output  # findings count
        assert "HIGH" in result.output

    @pytest.mark.asyncio
    async def test_dispatch_recon_when_no_surfaces(self, findings_doc):
        """Test dispatching recon when no attack surfaces exist."""
        # The orchestrator should dispatch recon when there are no surfaces
        summary = findings_doc.get_summary()

        assert summary["total_surfaces"] == 0
        assert summary["untested_surfaces"] == 0

        # This simulates the orchestrator's decision logic
        # When no surfaces exist, dispatch recon
        dispatch_tool = DispatchSubagentsTool(findings=findings_doc)

        # Verify the tool is configured correctly
        schema = dispatch_tool.get_schema()
        assert "recon" in schema.parameters["properties"]["subagent_type"]["enum"]

    @pytest.mark.asyncio
    async def test_dispatch_test_after_recon(self, findings_doc):
        """Test dispatching test subagent after recon has found surfaces."""
        # Add some attack surfaces from recon
        findings_doc.add_attack_surface(
            surface_id="surface-1",
            surface_type="endpoint",
            url="https://example.com/api/auth",
            description="Authentication endpoint",
            discovered_by="recon_subagent",
            priority="high",
        )

        # Get untested surfaces
        untested = findings_doc.get_untested_surfaces()
        assert len(untested) == 1
        assert untested[0].url == "https://example.com/api/auth"

        # Now test subagent should be dispatched
        dispatch_tool = DispatchSubagentsTool(findings=findings_doc)

        # Verify test is a valid subagent type
        schema = dispatch_tool.get_schema()
        assert "test" in schema.parameters["properties"]["subagent_type"]["enum"]

    def test_findings_shared_between_subagents(self, findings_doc):
        """Test that findings added by one subagent are visible to another."""
        # Simulate recon subagent adding a surface
        findings_doc.add_attack_surface(
            surface_id="shared-surface",
            surface_type="api",
            url="https://example.com/api/v2",
            description="New API discovered",
            discovered_by="recon_subagent",
        )

        # Create test subagent with same findings
        from tempo.agents.test_subagent import TestSubagent

        test_agent = TestSubagent(
            objective="Test discovered surfaces",
            findings=findings_doc,
        )

        # Test subagent should see the surface
        untested = test_agent.findings.get_untested_surfaces()
        assert len(untested) == 1
        assert untested[0].url == "https://example.com/api/v2"


class TestOrchestratorPromptBuilder:
    """Test PromptBuilder orchestrator prompt methods."""

    def test_build_orchestrator_prompt(self):
        """Test building orchestrator prompt."""
        builder = PromptBuilder()
        schemas = [
            {"function": {"name": "dispatch_subagents", "description": "Dispatch subagent"}},
            {"function": {"name": "read_findings", "description": "Read findings"}},
            {"function": {"name": "finalize_analysis", "description": "Finalize analysis"}},
        ]

        prompt = builder.build_orchestrator_prompt(
            tool_schemas=schemas,
            target="https://example.com",
            findings_summary="Attack Surfaces: 5 discovered, 2 tested\nFindings: 1 high",
        )

        assert "Orchestrator" in prompt
        assert "https://example.com" in prompt
        assert "dispatch_subagents" in prompt
        assert "finalize_analysis" in prompt
        assert "5 discovered" in prompt

    def test_build_orchestrator_prompt_empty_findings(self):
        """Test orchestrator prompt with no findings."""
        builder = PromptBuilder()
        schemas = [
            {"function": {"name": "dispatch_subagents", "description": "Dispatch"}},
        ]

        prompt = builder.build_orchestrator_prompt(
            tool_schemas=schemas,
            target="https://new-target.com",
            findings_summary="",
        )

        # Should include default message about starting recon
        assert "reconnaissance" in prompt.lower() or "recon" in prompt.lower()


class TestOrchestratorStateManagement:
    """Test orchestrator state and findings management."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_findings_persistence_across_agent_recreations(self, temp_dir):
        """Test that findings persist when agent is recreated."""
        findings_path = temp_dir / "persistent.yaml"

        # First agent adds data
        agent1 = OrchestratorAgent(
            target="https://example.com",
            findings_path=str(findings_path),
        )
        agent1.findings.add_attack_surface(
            surface_id="persistent-1",
            surface_type="endpoint",
            url="https://example.com/api",
            description="Test endpoint",
            discovered_by="test",
        )
        agent1.findings.save()

        # Second agent should see the data
        agent2 = OrchestratorAgent(
            target="https://different-target.com",  # Different target
            findings_path=str(findings_path),
        )

        # Should load existing document with original target
        assert agent2.findings._data.target == "https://example.com"
        assert len(agent2.findings._data.attack_surfaces) == 1
        assert agent2.findings._data.attack_surfaces[0].url == "https://example.com/api"

    def test_auto_generated_findings_path(self, temp_dir):
        """Test auto-generated findings path from target."""
        # Mock the findings directory creation
        with patch.object(Path, 'mkdir'):
            agent = OrchestratorAgent(
                target="https://sub.example.com/path",
            )

            # Force path generation
            safe_name = agent._make_safe_filename("https://sub.example.com/path")

            assert "sub.example.com" in safe_name
            assert "/" not in safe_name  # Should be escaped

    def test_max_iterations_passed_to_objective(self, temp_dir):
        """Test that max_iterations appears in the objective."""
        agent = OrchestratorAgent(
            target="https://example.com",
            findings_path=str(temp_dir / "test.yaml"),
            max_iterations=25,
        )

        objective = agent.build_objective()

        assert "25" in objective
