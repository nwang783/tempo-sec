"""Tests for DispatchSubagentTool."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys

from tempo.tools.dispatch_subagent import DispatchSubagentTool
from tempo.tools.base import ToolCategory
from tempo.findings.document import FindingsDocument


class TestDispatchSubagentTool:
    """Tests for DispatchSubagentTool."""

    @pytest.fixture
    def findings_doc(self):
        """Create a findings document for testing."""
        return FindingsDocument(target="https://example.com")

    def test_tool_properties(self, findings_doc):
        """Test tool has correct properties."""
        tool = DispatchSubagentTool(findings=findings_doc)

        assert tool.name == "dispatch_subagent"
        assert tool.category == ToolCategory.META
        assert "subagent" in tool.description.lower()

    def test_init(self, findings_doc):
        """Test tool initialization."""
        tool = DispatchSubagentTool(
            findings=findings_doc,
            container_manager=None,
        )

        assert tool._findings == findings_doc
        assert tool._container_manager is None

    @pytest.mark.asyncio
    async def test_execute_invalid_subagent_type(self, findings_doc):
        """Test execution with invalid subagent type."""
        tool = DispatchSubagentTool(findings=findings_doc)

        result = await tool.execute(
            subagent_type="invalid",
            objective="Test something",
        )

        assert result.success is False
        assert "Invalid subagent_type" in result.error

    def test_get_schema(self, findings_doc):
        """Test schema is properly formatted."""
        tool = DispatchSubagentTool(findings=findings_doc)
        schema = tool.get_schema()

        assert schema.name == "dispatch_subagent"
        required = schema.parameters.get("required", [])
        assert "subagent_type" in required
        assert "objective" in required

        props = schema.parameters["properties"]
        assert "subagent_type" in props
        assert props["subagent_type"]["enum"] == ["recon", "test"]
        assert "objective" in props
        assert "focus_area" in props
        assert "max_steps" in props

    def test_schema_defaults(self, findings_doc):
        """Test schema has correct defaults."""
        tool = DispatchSubagentTool(findings=findings_doc)
        schema = tool.get_schema()

        props = schema.parameters["properties"]
        assert props["focus_area"].get("default") == ""
        assert props["max_steps"].get("default") == 50

    def test_valid_subagent_types_in_schema(self, findings_doc):
        """Test that schema specifies valid subagent types."""
        tool = DispatchSubagentTool(findings=findings_doc)
        schema = tool.get_schema()

        subagent_types = schema.parameters["properties"]["subagent_type"]["enum"]
        assert "recon" in subagent_types
        assert "test" in subagent_types
        assert len(subagent_types) == 2


class TestDispatchSubagentToolWithMocks:
    """Tests for DispatchSubagentTool with mocked dependencies."""

    @pytest.fixture
    def findings_doc(self):
        """Create a findings document for testing."""
        return FindingsDocument(target="https://example.com")

    @pytest.mark.asyncio
    async def test_recon_subagent_creation(self, findings_doc):
        """Test that recon subagent is properly created."""
        tool = DispatchSubagentTool(findings=findings_doc)

        # Create mocks for the imports that happen inside execute
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=MagicMock(
            success=True,
            steps_taken=5,
            findings=[{"summary": "Found stuff", "surfaces_added": 3}],
            error=None,
        ))

        with patch.object(
            sys.modules['tempo.agents.recon_subagent'],
            'ReconSubagent',
            wraps=None
        ) as mock_recon_class:
            with patch('tempo.agent.runner.Agent', return_value=mock_agent):
                with patch('tempo.infra.llm.LiteLLMClient'):
                    # Configure the mock to return a proper subagent-like object
                    mock_subagent = MagicMock()
                    mock_subagent.model = "openai/gpt-4o-mini"
                    mock_subagent.initial_phase = MagicMock()
                    mock_subagent.name = "recon_subagent"
                    mock_subagent.create_tools.return_value = MagicMock()
                    mock_subagent.create_tools.return_value.get_schemas.return_value = []
                    mock_subagent.build_system_prompt.return_value = "System"
                    mock_subagent.build_objective.return_value = "Obj"
                    mock_recon_class.return_value = mock_subagent

                    result = await tool.execute(
                        subagent_type="recon",
                        objective="Find endpoints",
                    )

                    # Should have succeeded
                    assert result.success is True

    @pytest.mark.asyncio
    async def test_test_subagent_creation(self, findings_doc):
        """Test that test subagent is properly created."""
        tool = DispatchSubagentTool(findings=findings_doc)

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=MagicMock(
            success=True,
            steps_taken=10,
            findings=[{"summary": "Found vulns", "findings_added": 2}],
            error=None,
        ))

        with patch.object(
            sys.modules['tempo.agents.test_subagent'],
            'TestSubagent',
            wraps=None
        ) as mock_test_class:
            with patch('tempo.agent.runner.Agent', return_value=mock_agent):
                with patch('tempo.infra.llm.LiteLLMClient'):
                    mock_subagent = MagicMock()
                    mock_subagent.model = "openai/gpt-4o-mini"
                    mock_subagent.initial_phase = MagicMock()
                    mock_subagent.name = "test_subagent"
                    mock_subagent.create_tools.return_value = MagicMock()
                    mock_subagent.create_tools.return_value.get_schemas.return_value = []
                    mock_subagent.build_system_prompt.return_value = "System"
                    mock_subagent.build_objective.return_value = "Obj"
                    mock_test_class.return_value = mock_subagent

                    result = await tool.execute(
                        subagent_type="test",
                        objective="Test for SQL injection",
                    )

                    assert result.success is True
