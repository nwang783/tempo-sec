"""Integration tests for subagent dispatch flow."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tempo.findings.document import FindingsDocument
from tempo.agents.recon_subagent import ReconSubagent
from tempo.agents.test_subagent import TestSubagent
from tempo.tools.dispatch_subagent import DispatchSubagentTool
from tempo.tools.complete_subtask import CompleteSubtaskTool
from tempo.agent.step_handler import StepHandler, SpecialToolResult
from tempo.context.frame import ToolCall
from tempo.context.store import ContextStore


class TestSubagentDispatchIntegration:
    """Integration tests for subagent dispatch workflow."""

    @pytest.fixture
    def findings_doc(self):
        """Create a findings document for testing."""
        return FindingsDocument(target="https://example.com")

    def test_complete_subtask_integration_with_step_handler(self):
        """Test that complete_subtask is properly handled by step handler."""
        from tempo.tools.registry import ToolRegistry

        tools = ToolRegistry()
        handler = StepHandler(tools)

        # Simulate a complete_subtask tool call
        tool_call = ToolCall(
            id="subtask-123",
            tool_name="complete_subtask",
            input={"summary": "Discovered 5 endpoints"},
            metadata={
                "subtask_complete": True,
                "summary": "Discovered 5 API endpoints on the target",
                "surfaces_added": 5,
                "findings_added": 0,
                "notes": "Login endpoint looks promising",
            },
        )

        result = handler.process_special_tool(tool_call)

        assert result is not None
        assert isinstance(result, SpecialToolResult)
        assert result.tool_name == "complete_subtask"
        assert result.should_continue is False
        assert result.findings is not None
        assert result.findings["summary"] == "Discovered 5 API endpoints on the target"
        assert result.findings["surfaces_added"] == 5
        assert result.findings["notes"] == "Login endpoint looks promising"

    def test_recon_subagent_tools_include_complete_subtask(self, findings_doc):
        """Test that ReconSubagent has complete_subtask tool."""
        agent = ReconSubagent(
            objective="Find endpoints",
            findings=findings_doc,
        )
        context = ContextStore()

        tools = agent.create_tools(context=context)
        tool_names = tools.list_tools()

        assert "complete_subtask" in tool_names

    def test_test_subagent_tools_include_complete_subtask(self, findings_doc):
        """Test that TestSubagent has complete_subtask tool."""
        agent = TestSubagent(
            objective="Test for vulnerabilities",
            findings=findings_doc,
        )
        context = ContextStore()

        tools = agent.create_tools(context=context)
        tool_names = tools.list_tools()

        assert "complete_subtask" in tool_names

    def test_recon_subagent_shares_findings_document(self, findings_doc):
        """Test that ReconSubagent tools modify the shared findings document."""
        agent = ReconSubagent(
            objective="Find endpoints",
            findings=findings_doc,
        )
        context = ContextStore()

        tools = agent.create_tools(context=context)

        # Get the add_attack_surface tool
        add_surface_tool = tools.get("add_attack_surface")
        assert add_surface_tool is not None

        # The tool should reference the same findings document
        assert add_surface_tool.findings == findings_doc

    def test_test_subagent_shares_findings_document(self, findings_doc):
        """Test that TestSubagent tools modify the shared findings document."""
        agent = TestSubagent(
            objective="Test vulnerabilities",
            findings=findings_doc,
        )
        context = ContextStore()

        tools = agent.create_tools(context=context)

        # Get the add_finding tool
        add_finding_tool = tools.get("add_finding")
        assert add_finding_tool is not None

        # The tool should reference the same findings document
        assert add_finding_tool.findings == findings_doc

    @pytest.mark.asyncio
    async def test_complete_subtask_execution(self):
        """Test complete_subtask tool execution."""
        tool = CompleteSubtaskTool()

        result = await tool.execute(
            summary="Discovered 3 API endpoints and 2 forms",
            surfaces_added=5,
            findings_added=0,
            notes="Login form uses JWT authentication",
        )

        assert result.success is True
        assert result.metadata["subtask_complete"] is True
        assert result.metadata["summary"] == "Discovered 3 API endpoints and 2 forms"
        assert result.metadata["surfaces_added"] == 5

    def test_dispatch_tool_creates_correct_subagent_type(self, findings_doc):
        """Test that dispatch tool creates the correct subagent type."""
        tool = DispatchSubagentTool(findings=findings_doc)

        # Test schema specifies valid types
        schema = tool.get_schema()
        subagent_types = schema.parameters["properties"]["subagent_type"]["enum"]

        assert "recon" in subagent_types
        assert "test" in subagent_types

    @pytest.mark.asyncio
    async def test_full_recon_dispatch_flow(self, findings_doc):
        """Test full recon subagent dispatch flow with mocks."""
        import sys
        tool = DispatchSubagentTool(findings=findings_doc)

        # Create mock agent that will be used by the dispatch tool
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=MagicMock(
            success=True,
            steps_taken=10,
            findings=[{
                "summary": "Found 5 API endpoints",
                "surfaces_added": 5,
                "findings_added": 0,
                "notes": "REST API at /api/v1",
            }],
            error=None,
        ))

        with patch.object(
            sys.modules['tempo.agents.recon_subagent'],
            'ReconSubagent',
            wraps=None
        ) as mock_recon_class:
            with patch('tempo.agent.runner.Agent', return_value=mock_agent):
                with patch('tempo.infra.llm.LiteLLMClient'):
                    # Setup mock subagent
                    mock_subagent = MagicMock()
                    mock_subagent.model = "openai/gpt-4o-mini"
                    mock_subagent.name = "recon_subagent"
                    mock_subagent.initial_phase = MagicMock()
                    mock_subagent.create_tools.return_value = MagicMock()
                    mock_subagent.create_tools.return_value.get_schemas.return_value = []
                    mock_subagent.build_system_prompt.return_value = "System prompt"
                    mock_subagent.build_objective.return_value = "Objective"
                    mock_recon_class.return_value = mock_subagent

                    # Execute dispatch
                    result = await tool.execute(
                        subagent_type="recon",
                        objective="Discover API endpoints",
                        focus_area="REST API",
                        max_steps=20,
                    )

                    # Verify result
                    assert result.success is True
                    assert "completed" in result.output.lower()
                    assert "10 steps" in result.output
                    assert result.metadata["subagent_type"] == "recon"
                    assert result.metadata["steps_taken"] == 10
                    assert result.metadata["summary"] == "Found 5 API endpoints"

    @pytest.mark.asyncio
    async def test_full_test_dispatch_flow(self, findings_doc):
        """Test full test subagent dispatch flow with mocks."""
        import sys
        tool = DispatchSubagentTool(findings=findings_doc)

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=MagicMock(
            success=True,
            steps_taken=15,
            findings=[{
                "summary": "Found SQL injection vulnerability",
                "surfaces_added": 0,
                "findings_added": 1,
                "notes": "Login endpoint vulnerable",
            }],
            error=None,
        ))

        with patch.object(
            sys.modules['tempo.agents.test_subagent'],
            'TestSubagent',
            wraps=None
        ) as mock_test_class:
            with patch('tempo.agent.runner.Agent', return_value=mock_agent):
                with patch('tempo.infra.llm.LiteLLMClient'):
                    # Setup mock subagent
                    mock_subagent = MagicMock()
                    mock_subagent.model = "openai/gpt-4o-mini"
                    mock_subagent.name = "test_subagent"
                    mock_subagent.initial_phase = MagicMock()
                    mock_subagent.create_tools.return_value = MagicMock()
                    mock_subagent.create_tools.return_value.get_schemas.return_value = []
                    mock_subagent.build_system_prompt.return_value = "System prompt"
                    mock_subagent.build_objective.return_value = "Objective"
                    mock_test_class.return_value = mock_subagent

                    # Execute dispatch
                    result = await tool.execute(
                        subagent_type="test",
                        objective="Test for SQL injection",
                        focus_area="Login endpoint",
                        max_steps=30,
                    )

                    # Verify result
                    assert result.success is True
                    assert "completed" in result.output.lower()
                    assert "15 steps" in result.output
                    assert result.metadata["subagent_type"] == "test"
                    assert result.metadata["findings_added"] == 1


class TestPromptBuilderSubagentPrompts:
    """Test PromptBuilder subagent prompt methods."""

    def test_build_recon_subagent_prompt(self):
        """Test building recon subagent prompt."""
        from tempo.prompts.builder import PromptBuilder

        builder = PromptBuilder()
        schemas = [
            {"function": {"name": "shell", "description": "Run commands"}},
            {"function": {"name": "add_attack_surface", "description": "Add surface"}},
        ]

        prompt = builder.build_recon_subagent_prompt(
            tool_schemas=schemas,
            objective="Find API endpoints",
            findings_context="Target: example.com, 0 surfaces",
            focus_area="REST API",
        )

        assert "Reconnaissance" in prompt
        assert "Find API endpoints" in prompt
        assert "REST API" in prompt
        assert "shell" in prompt
        assert "add_attack_surface" in prompt

    def test_build_test_subagent_prompt(self):
        """Test building test subagent prompt."""
        from tempo.prompts.builder import PromptBuilder

        builder = PromptBuilder()
        schemas = [
            {"function": {"name": "shell", "description": "Run commands"}},
            {"function": {"name": "add_finding", "description": "Add finding"}},
        ]

        prompt = builder.build_test_subagent_prompt(
            tool_schemas=schemas,
            objective="Test for SQL injection",
            attack_surfaces_context="3 untested surfaces",
        )

        assert "Test" in prompt
        assert "Test for SQL injection" in prompt
        assert "3 untested surfaces" in prompt
        assert "shell" in prompt
        assert "add_finding" in prompt
