"""Tests for TestSubagent."""

import pytest

from tempo.agents.test_subagent import TestSubagent
from tempo.context.store import ContextStore
from tempo.findings.document import FindingsDocument
from tempo.prompts.builder import PromptBuilder


class TestTestSubagent:
    """Tests for TestSubagent definition."""

    @pytest.fixture
    def findings_doc(self):
        """Create a findings document for testing."""
        return FindingsDocument(target="https://example.com")

    def test_init(self, findings_doc):
        """Test TestSubagent initialization."""
        agent = TestSubagent(
            objective="Test SQL injection on login endpoint",
            findings=findings_doc,
            focus_area="Login form",
        )

        assert agent.objective == "Test SQL injection on login endpoint"
        assert agent.findings == findings_doc
        assert agent.focus_area == "Login form"
        assert agent.name == "test_subagent"

    def test_init_without_focus_area(self, findings_doc):
        """Test initialization without focus area."""
        agent = TestSubagent(
            objective="General testing",
            findings=findings_doc,
        )

        assert agent.focus_area == ""

    def test_model_is_fast(self, findings_doc):
        """Test that test subagent uses a fast model."""
        agent = TestSubagent(objective="test", findings=findings_doc)

        # Should use a lightweight model for fast execution
        assert "mini" in agent.model or "4o" in agent.model

    def test_description(self, findings_doc):
        """Test agent description."""
        agent = TestSubagent(objective="test", findings=findings_doc)

        assert "testing" in agent.description.lower()
        assert "finding" in agent.description.lower()

    def test_create_tools_has_required_tools(self, findings_doc):
        """Test that test subagent has required tools."""
        agent = TestSubagent(objective="test", findings=findings_doc)
        context = ContextStore()

        tools = agent.create_tools(context=context)
        tool_names = tools.list_tools()

        # Core testing tools
        assert "shell" in tool_names
        assert "file_read" in tool_names
        assert "file_write" in tool_names
        # NOTE: browser subagent intentionally disabled for now.
        # assert "browser_task" in tool_names

        # Findings document tools for testing
        assert "add_finding" in tool_names
        assert "mark_surface_tested" in tool_names

        # Meta tools
        assert "summarize_previous_tool_output" in tool_names
        assert "complete_subtask" in tool_names

    def test_create_tools_no_recon_tools(self, findings_doc):
        """Test that test subagent doesn't have recon-specific tools."""
        agent = TestSubagent(objective="test", findings=findings_doc)
        context = ContextStore()

        tools = agent.create_tools(context=context)
        tool_names = tools.list_tools()

        # Should NOT have recon-specific tools
        assert "add_attack_surface" not in tool_names
        assert "update_recon_summary" not in tool_names

    def test_build_objective_includes_objective(self, findings_doc):
        """Test that objective includes the provided objective."""
        agent = TestSubagent(
            objective="Test XSS vulnerabilities",
            findings=findings_doc,
            focus_area="Search forms",
        )

        objective = agent.build_objective()

        assert "Test XSS vulnerabilities" in objective
        assert "Search forms" in objective
        assert "complete_subtask" in objective

    def test_build_objective_without_focus_area(self, findings_doc):
        """Test objective when no focus area is provided."""
        agent = TestSubagent(
            objective="General testing",
            findings=findings_doc,
        )

        objective = agent.build_objective()

        assert "General testing" in objective
        assert "complete_subtask" in objective

    def test_build_system_prompt(self, findings_doc):
        """Test system prompt building."""
        agent = TestSubagent(
            objective="Test for vulnerabilities",
            findings=findings_doc,
        )
        prompts = PromptBuilder()
        mock_schemas = [
            {"function": {"name": "shell", "description": "Execute commands"}},
            {"function": {"name": "add_finding", "description": "Add finding"}},
        ]

        prompt = agent.build_system_prompt(
            prompts=prompts,
            tool_schemas=mock_schemas,
            scope_description="Test scope",
        )

        assert "Test" in prompt
        assert "shell" in prompt
        assert "add_finding" in prompt

    def test_attack_surfaces_context_generation_empty(self, findings_doc):
        """Test attack surfaces context with no surfaces."""
        agent = TestSubagent(
            objective="Test surfaces",
            findings=findings_doc,
        )

        context = agent._get_attack_surfaces_context()

        assert "No untested attack surfaces" in context

    def test_attack_surfaces_context_generation_with_surfaces(self, findings_doc):
        """Test attack surfaces context with surfaces present."""
        # Add some attack surfaces
        findings_doc.add_attack_surface(
            surface_id="surf-1",
            surface_type="endpoint",
            url="https://example.com/api/login",
            description="Login endpoint",
            discovered_by="recon",
            priority="high",
        )
        findings_doc.add_attack_surface(
            surface_id="surf-2",
            surface_type="form",
            url="https://example.com/search",
            description="Search form",
            discovered_by="recon",
            priority="medium",
        )

        agent = TestSubagent(
            objective="Test surfaces",
            findings=findings_doc,
        )

        context = agent._get_attack_surfaces_context()

        assert "2 untested attack surfaces" in context
        assert "HIGH" in context
        assert "MEDIUM" in context
        assert "endpoint" in context
        assert "form" in context


class TestTestSubagentRegistration:
    """Tests for TestSubagent registration."""

    def test_registered(self):
        """Test that TestSubagent is properly registered."""
        from tempo.agents import list_agents, get_agent_class

        agents = list_agents()

        assert "test_subagent" in agents

        agent_class = get_agent_class("test_subagent")
        assert agent_class == TestSubagent
