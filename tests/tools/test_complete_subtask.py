"""Tests for CompleteSubtaskTool."""

import pytest

from tempo.tools.complete_subtask import CompleteSubtaskTool
from tempo.tools.base import ToolCategory


class TestCompleteSubtaskTool:
    """Tests for CompleteSubtaskTool."""

    def test_tool_properties(self):
        """Test tool has correct properties."""
        tool = CompleteSubtaskTool()

        assert tool.name == "complete_subtask"
        assert tool.category == ToolCategory.META
        assert "subtask" in tool.description.lower()

    @pytest.mark.asyncio
    async def test_execute_basic_summary(self):
        """Test execution with just a summary."""
        tool = CompleteSubtaskTool()

        result = await tool.execute(
            summary="Discovered 5 attack surfaces on the target"
        )

        assert result.success is True
        assert "Subtask completed" in result.output
        assert "Discovered 5 attack surfaces" in result.output
        assert result.metadata.get("subtask_complete") is True
        assert result.metadata.get("summary") == "Discovered 5 attack surfaces on the target"
        assert result.metadata.get("surfaces_added") == 0
        assert result.metadata.get("findings_added") == 0

    @pytest.mark.asyncio
    async def test_execute_with_surfaces(self):
        """Test execution with surfaces_added."""
        tool = CompleteSubtaskTool()

        result = await tool.execute(
            summary="Reconnaissance complete",
            surfaces_added=7,
        )

        assert result.success is True
        assert "Attack surfaces added: 7" in result.output
        assert result.metadata.get("surfaces_added") == 7

    @pytest.mark.asyncio
    async def test_execute_with_findings(self):
        """Test execution with findings_added."""
        tool = CompleteSubtaskTool()

        result = await tool.execute(
            summary="Testing complete",
            findings_added=3,
        )

        assert result.success is True
        assert "Findings added: 3" in result.output
        assert result.metadata.get("findings_added") == 3

    @pytest.mark.asyncio
    async def test_execute_with_notes(self):
        """Test execution with notes."""
        tool = CompleteSubtaskTool()

        result = await tool.execute(
            summary="Testing complete",
            notes="Login endpoint is most vulnerable",
        )

        assert result.success is True
        assert "Notes: Login endpoint" in result.output
        assert result.metadata.get("notes") == "Login endpoint is most vulnerable"

    @pytest.mark.asyncio
    async def test_execute_all_fields(self):
        """Test execution with all fields populated."""
        tool = CompleteSubtaskTool()

        result = await tool.execute(
            summary="Full recon and testing complete",
            surfaces_added=5,
            findings_added=2,
            notes="Critical SQL injection found",
            purpose="Complete the testing subtask",
        )

        assert result.success is True
        assert "Full recon and testing complete" in result.output
        assert "Attack surfaces added: 5" in result.output
        assert "Findings added: 2" in result.output
        assert "Notes: Critical SQL injection" in result.output
        assert result.metadata["subtask_complete"] is True
        assert result.metadata["surfaces_added"] == 5
        assert result.metadata["findings_added"] == 2

    def test_get_schema(self):
        """Test schema is properly formatted."""
        tool = CompleteSubtaskTool()
        schema = tool.get_schema()

        assert schema.name == "complete_subtask"
        assert "summary" in schema.parameters.get("required", [])
        assert "summary" in schema.parameters["properties"]
        assert "surfaces_added" in schema.parameters["properties"]
        assert "findings_added" in schema.parameters["properties"]
        assert "notes" in schema.parameters["properties"]

    def test_schema_has_defaults(self):
        """Test schema has correct defaults."""
        tool = CompleteSubtaskTool()
        schema = tool.get_schema()

        props = schema.parameters["properties"]
        assert props["surfaces_added"].get("default") == 0
        assert props["findings_added"].get("default") == 0
        assert props["notes"].get("default") == ""

    @pytest.mark.asyncio
    async def test_execute_with_limitations(self):
        """Test execution with limitations field."""
        tool = CompleteSubtaskTool()

        result = await tool.execute(
            summary="Reconnaissance complete",
            surfaces_added=5,
            limitations="Could not access /admin (403). Rate limited after 100 requests.",
        )

        assert result.success is True
        assert "Limitations:" in result.output
        assert "/admin" in result.output
        assert result.metadata.get("limitations") == (
            "Could not access /admin (403). Rate limited after 100 requests."
        )

    def test_schema_includes_limitations(self):
        """Test schema has limitations field."""
        tool = CompleteSubtaskTool()
        schema = tool.get_schema()

        props = schema.parameters["properties"]
        assert "limitations" in props
        assert props["limitations"].get("default") == ""
        assert "blockers" in props["limitations"].get("description", "").lower()

