"""Tests for OrchestratorAgent."""

import tempfile
import pytest
from pathlib import Path

from tempo.agents.orchestrator import OrchestratorAgent
from tempo.context.store import ContextStore
from tempo.findings.document import FindingsDocument
from tempo.prompts.builder import PromptBuilder


class TestOrchestratorAgent:
    """Tests for OrchestratorAgent definition."""

    def test_init(self):
        """Test OrchestratorAgent initialization."""
        agent = OrchestratorAgent(
            target="https://example.com",
            findings_path="./findings/test.yaml",
            max_iterations=15,
        )

        assert agent.target == "https://example.com"
        assert agent._findings_path == "./findings/test.yaml"
        assert agent._max_iterations == 15
        assert agent.name == "orchestrator"

    def test_init_defaults(self):
        """Test initialization with defaults."""
        agent = OrchestratorAgent(target="https://example.com")

        assert agent._findings_path is None
        assert agent._max_iterations == 10

    def test_description(self):
        """Test agent description."""
        agent = OrchestratorAgent(target="https://example.com")

        assert "orchestrator" in agent.description.lower()
        assert "coordinates" in agent.description.lower() or "subagent" in agent.description.lower()

    def test_findings_lazy_loading_auto_path(self):
        """Test findings document lazy loading with auto-generated path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Use a path within the temp directory
            agent = OrchestratorAgent(target="https://example.com")
            # Override the auto-path to use temp dir
            agent._findings_path = f"{tmpdir}/example_com.yaml"

            # First access should create the document
            findings = agent.findings

            assert findings is not None
            assert findings._data.target == "https://example.com"

    def test_findings_lazy_loading_existing_file(self):
        """Test findings document lazy loading from existing file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create an existing findings file
            findings_path = Path(tmpdir) / "existing.yaml"
            existing_doc = FindingsDocument(
                target="https://existing-target.com",
                file_path=str(findings_path),
            )
            existing_doc.add_attack_surface(
                surface_id="test-1",
                surface_type="endpoint",
                url="https://existing-target.com/api",
                description="Test endpoint",
                discovered_by="test",
            )
            existing_doc.save()

            # Create agent pointing to existing file
            agent = OrchestratorAgent(
                target="https://new-target.com",  # Different target
                findings_path=str(findings_path),
            )

            # Should load existing document (preserving target from file)
            findings = agent.findings

            assert findings is not None
            assert findings._data.target == "https://existing-target.com"
            assert len(findings._data.attack_surfaces) == 1

    def test_findings_lazy_loading_new_file_at_path(self):
        """Test findings document creation at specified non-existing path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            findings_path = Path(tmpdir) / "subdir" / "new.yaml"

            agent = OrchestratorAgent(
                target="https://new-target.com",
                findings_path=str(findings_path),
            )

            # Should create new document at specified path
            findings = agent.findings

            assert findings is not None
            assert findings._data.target == "https://new-target.com"
            assert findings.file_path == str(findings_path)

    def test_make_safe_filename(self):
        """Test safe filename generation from targets."""
        agent = OrchestratorAgent(target="test")

        # Test various inputs
        assert agent._make_safe_filename("https://example.com") == "example.com"
        assert agent._make_safe_filename("http://sub.example.com") == "sub.example.com"
        assert agent._make_safe_filename("example.com/path/to/resource") == "example.com_path_to_resource"
        assert agent._make_safe_filename("https://ex@mple.com?query=1") == "ex_mple.com_query_1"

        # Very long URL should be truncated
        long_url = "https://example.com/" + "a" * 100
        result = agent._make_safe_filename(long_url)
        assert len(result) <= 50

    def test_create_tools_has_required_tools(self):
        """Test that orchestrator has required tools."""
        agent = OrchestratorAgent(target="https://example.com")
        context = ContextStore()

        tools = agent.create_tools(context=context)
        tool_names = tools.list_tools()

        # Orchestrator should NOT have execution tools (delegates to subagents)
        assert "shell" not in tool_names
        assert "file_read" not in tool_names
        assert "file_write" not in tool_names

        # Subagent dispatch tool - key orchestration capability
        assert "dispatch_subagents" in tool_names

        # Findings management - read only (subagents handle writes)
        assert "read_findings" in tool_names
        assert "add_finding" not in tool_names
        assert "add_attack_surface" not in tool_names

        # Meta tools
        assert "summarize_previous_tool_output" in tool_names
        assert "finalize_analysis" in tool_names

    def test_create_tools_no_phase_transition(self):
        """Test that orchestrator doesn't have phase transition tools."""
        agent = OrchestratorAgent(target="https://example.com")
        context = ContextStore()

        tools = agent.create_tools(context=context)
        tool_names = tools.list_tools()

        # Should NOT have phase transition (orchestrator manages its own flow)
        assert "transition_phase" not in tool_names
        assert "continue_analysis" not in tool_names

    def test_build_objective_includes_target(self):
        """Test that objective includes the target."""
        agent = OrchestratorAgent(
            target="https://example.com",
            max_iterations=5,
        )

        objective = agent.build_objective()

        assert "https://example.com" in objective
        assert "5" in objective  # max iterations
        assert "read_findings" in objective
        assert "dispatch_subagents" in objective
        assert "finalize_analysis" in objective

    def test_build_objective_with_override_target(self):
        """Test objective with target override."""
        agent = OrchestratorAgent(target="https://original.com")

        objective = agent.build_objective(target="https://override.com")

        # The main target in the objective should be the override
        assert "**Target:** https://override.com" in objective
        # Note: The findings summary may still reference original.com
        # since the FindingsDocument was created with the original target.
        # This is expected behavior - the override is mainly for display.

    def test_build_system_prompt(self):
        """Test system prompt building."""
        with tempfile.TemporaryDirectory() as tmpdir:
            findings_path = Path(tmpdir) / "test.yaml"
            agent = OrchestratorAgent(
                target="https://example.com",
                findings_path=str(findings_path),
            )
            prompts = PromptBuilder()
            mock_schemas = [
                {"function": {"name": "shell", "description": "Execute commands"}},
                {"function": {"name": "dispatch_subagents", "description": "Dispatch subagent"}},
                {"function": {"name": "finalize_analysis", "description": "Finalize analysis"}},
            ]

            prompt = agent.build_system_prompt(
                prompts=prompts,
                tool_schemas=mock_schemas,
                scope_description="Test scope",
            )

            assert "Orchestrator" in prompt
            assert "https://example.com" in prompt
            assert "shell" in prompt
            assert "dispatch_subagents" in prompt

    def test_get_findings_summary_empty(self):
        """Test findings summary generation with empty document."""
        with tempfile.TemporaryDirectory() as tmpdir:
            findings_path = Path(tmpdir) / "test.yaml"
            agent = OrchestratorAgent(
                target="https://example.com",
                findings_path=str(findings_path),
            )

            summary = agent._get_findings_summary()

            assert "https://example.com" in summary
            assert "0 discovered" in summary or "Attack Surfaces: 0" in summary

    def test_get_findings_summary_with_data(self):
        """Test findings summary generation with populated document."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create findings with data
            findings_path = Path(tmpdir) / "test.yaml"
            doc = FindingsDocument(
                target="https://example.com",
                file_path=str(findings_path),
            )
            doc.add_attack_surface(
                surface_id="test-1",
                surface_type="endpoint",
                url="https://example.com/api",
                description="API endpoint",
                discovered_by="recon",
            )
            doc.add_finding(
                finding_id="finding-1",
                title="Test XSS",
                severity="high",
                status="confirmed",
                description="XSS vulnerability",
                evidence="Test evidence",
                discovered_by="test",
            )
            doc.save()

            agent = OrchestratorAgent(
                target="https://example.com",
                findings_path=str(findings_path),
            )

            summary = agent._get_findings_summary()

            assert "https://example.com" in summary
            assert "1 discovered" in summary or "Attack Surfaces: 1" in summary
            assert "High: 1" in summary or "high" in summary.lower()


class TestOrchestratorAgentRegistration:
    """Tests for OrchestratorAgent registration."""

    def test_registered(self):
        """Test that OrchestratorAgent is properly registered."""
        from tempo.agents import list_agents, get_agent_class

        agents = list_agents()

        assert "orchestrator" in agents

        agent_class = get_agent_class("orchestrator")
        assert agent_class == OrchestratorAgent

    def test_get_agent_factory(self):
        """Test that get_agent factory works correctly."""
        from tempo.agents import get_agent

        agent = get_agent(
            "orchestrator",
            target="https://example.com",
            max_iterations=5,
        )

        assert isinstance(agent, OrchestratorAgent)
        assert agent.target == "https://example.com"
        assert agent._max_iterations == 5
