"""Tests for CompleteBrowserTaskTool."""

import pytest

from tempo.tools.complete_browser_task import CompleteBrowserTaskTool
from tempo.tools.base import ToolCategory


class TestCompleteBrowserTaskTool:
    """Tests for CompleteBrowserTaskTool."""

    def test_tool_properties(self):
        """Test tool has correct properties."""
        tool = CompleteBrowserTaskTool()

        assert tool.name == "complete_browser_task"
        assert tool.category == ToolCategory.META
        assert "browser" in tool.description.lower()

    @pytest.mark.asyncio
    async def test_execute_basic(self):
        """Test execution with just findings."""
        tool = CompleteBrowserTaskTool()

        result = await tool.execute(findings="Login successful")

        assert result.success is True
        assert "Login successful" in result.output
        assert result.metadata.get("browser_task_complete") is True
        assert result.metadata.get("findings") == "Login successful"

    @pytest.mark.asyncio
    async def test_execute_with_limitations(self):
        """Test execution with limitations field."""
        tool = CompleteBrowserTaskTool()

        result = await tool.execute(
            findings="Partial exploration complete",
            success=True,
            limitations="Session expired after 5 minutes. CAPTCHA blocked further navigation.",
        )

        assert result.success is True
        assert "Limitations:" in result.output
        assert "Session expired" in result.output
        assert result.metadata.get("limitations") == (
            "Session expired after 5 minutes. CAPTCHA blocked further navigation."
        )

    @pytest.mark.asyncio
    async def test_execute_with_all_fields(self):
        """Test execution with all fields populated."""
        tool = CompleteBrowserTaskTool()

        result = await tool.execute(
            findings="Found admin panel",
            success=True,
            extracted_data="Admin users: alice, bob",
            limitations="Could not access settings page",
        )

        assert result.success is True
        assert "Found admin panel" in result.output
        assert "Extracted data" in result.output
        assert "Limitations:" in result.output
        assert result.metadata.get("extracted_data") == "Admin users: alice, bob"
        assert result.metadata.get("limitations") == "Could not access settings page"

    def test_schema_includes_limitations(self):
        """Test schema has limitations field."""
        tool = CompleteBrowserTaskTool()
        schema = tool.get_schema()

        props = schema.parameters["properties"]
        assert "limitations" in props
        assert props["limitations"].get("default") == ""
        assert "limitations" in props["limitations"].get("description", "").lower()
