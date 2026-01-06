"""Tests for ReconSubagent."""

import pytest

from tempo.agents.recon_subagent import ReconSubagent
from tempo.context.store import ContextStore
from tempo.findings.document import FindingsDocument
from tempo.prompts.builder import PromptBuilder


class TestReconSubagent:
    """Tests for ReconSubagent definition."""

    @pytest.fixture
    def findings_doc(self):
        """Create a findings document for testing."""
        return FindingsDocument(target="https://example.com")

    def test_init(self, findings_doc):
        """Test ReconSubagent initialization."""
        agent = ReconSubagent(
            objective="Discover all API endpoints",
            findings=findings_doc,
            focus_area="REST API",
        )

        assert agent.objective == "Discover all API endpoints"
        assert agent.findings == findings_doc
        assert agent.focus_area == "REST API"
        assert agent.name == "recon_subagent"

    def test_init_without_focus_area(self, findings_doc):
        """Test initialization without focus area."""
        agent = ReconSubagent(
            objective="General recon",
            findings=findings_doc,
        )

        assert agent.focus_area == ""

    def test_model_is_fast(self, findings_doc):
        """Test that recon subagent uses a fast model."""
        agent = ReconSubagent(objective="test", findings=findings_doc)

        # Should use a lightweight model for fast execution
        assert "mini" in agent.model or "4o" in agent.model

    def test_description(self, findings_doc):
        """Test agent description."""
        agent = ReconSubagent(objective="test", findings=findings_doc)

        assert "reconnaissance" in agent.description.lower()
        assert "attack surface" in agent.description.lower()

    def test_create_tools_has_required_tools(self, findings_doc):
        """Test that recon subagent has required tools."""
        agent = ReconSubagent(objective="test", findings=findings_doc)
        context = ContextStore()

        tools = agent.create_tools(context=context)
        tool_names = tools.list_tools()

        # Core reconnaissance tools
        assert "shell" in tool_names
        assert "file_read" in tool_names
        assert "file_write" in tool_names
        # NOTE: browser subagent intentionally disabled for now.
        # assert "browser_task" in tool_names

        # Findings document tools for recon
        assert "add_attack_surface" in tool_names
        assert "update_recon_summary" in tool_names

        # Meta tools
        assert "summarize_previous_tool_output" in tool_names
        assert "complete_subtask" in tool_names

    def test_create_tools_no_testing_tools(self, findings_doc):
        """Test that recon subagent doesn't have testing-specific tools."""
        agent = ReconSubagent(objective="test", findings=findings_doc)
        context = ContextStore()

        tools = agent.create_tools(context=context)
        tool_names = tools.list_tools()

        # Should NOT have testing-specific tools
        assert "add_finding" not in tool_names
        assert "mark_surface_tested" not in tool_names

    def test_build_objective_includes_objective(self, findings_doc):
        """Test that objective includes the provided objective."""
        agent = ReconSubagent(
            objective="Find all login endpoints",
            findings=findings_doc,
            focus_area="Authentication",
        )

        objective = agent.build_objective()

        assert "Find all login endpoints" in objective
        assert "Authentication" in objective
        assert "complete_subtask" in objective

    def test_build_objective_without_focus_area(self, findings_doc):
        """Test objective when no focus area is provided."""
        agent = ReconSubagent(
            objective="General reconnaissance",
            findings=findings_doc,
        )

        objective = agent.build_objective()

        assert "General reconnaissance" in objective
        assert "complete_subtask" in objective

    def test_build_system_prompt(self, findings_doc):
        """Test system prompt building."""
        agent = ReconSubagent(
            objective="Find attack surfaces",
            findings=findings_doc,
        )
        prompts = PromptBuilder()
        mock_schemas = [
            {"function": {"name": "shell", "description": "Execute commands"}},
            {"function": {"name": "add_attack_surface", "description": "Add surface"}},
        ]

        prompt = agent.build_system_prompt(
            prompts=prompts,
            tool_schemas=mock_schemas,
            scope_description="Test scope",
        )

        assert "Reconnaissance" in prompt
        assert "shell" in prompt
        assert "add_attack_surface" in prompt

    def test_findings_context_generation(self, findings_doc):
        """Test that findings context is generated correctly."""
        # Add some data to findings
        findings_doc.add_attack_surface(
            surface_id="test-1",
            surface_type="endpoint",
            url="https://example.com/api",
            description="Test endpoint",
            discovered_by="recon",
        )

        agent = ReconSubagent(
            objective="Continue recon",
            findings=findings_doc,
        )

        context = agent._get_findings_context()

        assert "https://example.com" in context
        assert "Attack Surfaces: 1" in context


class TestReconSubagentRegistration:
    """Tests for ReconSubagent registration."""

    def test_registered(self):
        """Test that ReconSubagent is properly registered."""
        from tempo.agents import list_agents, get_agent_class

        agents = list_agents()

        assert "recon_subagent" in agents

        agent_class = get_agent_class("recon_subagent")
        assert agent_class == ReconSubagent
