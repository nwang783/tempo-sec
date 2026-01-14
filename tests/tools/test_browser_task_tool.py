"""Tests for BrowserTaskTool with browser-use integration."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tempo.tools.browser_task_tool import BrowserTaskTool


class TestBrowserTaskTool:
    def test_init(self):
        tool = BrowserTaskTool()
        assert tool.name == "browser_task"

    def test_schema_includes_required_params(self):
        """Test that schema includes all required parameters."""
        tool = BrowserTaskTool()
        schema = tool.get_schema()

        assert schema.name == "browser_task"
        props = schema.parameters["properties"]
        assert "task" in props
        assert "url" in props
        assert "scope" in props
        assert "use_browser_use_llm" in props
        assert schema.parameters["required"] == ["task"]

    @pytest.mark.asyncio
    async def test_execute_handles_kwargs_and_config(self):
        """Test that execute accepts extra kwargs and configures browser-use agent correctly."""
        tool = BrowserTaskTool()

        # Create mock browser-use components
        mock_agent = MagicMock()
        mock_history = MagicMock()
        mock_history.history = [MagicMock(), MagicMock()]  # 2 steps
        mock_history.final_result = MagicMock(return_value="Task completed successfully")
        mock_history.extracted_content = MagicMock(return_value=None)
        mock_agent.run = AsyncMock(return_value=mock_history)

        mock_browser = MagicMock()
        mock_browser.close = AsyncMock()

        mock_tools = MagicMock()

        with patch("tempo.agents.browser.BrowserAgent") as mock_browser_agent:
            mock_def = MagicMock()
            mock_def.create_browser_use_agent = MagicMock(
                return_value=(mock_agent, mock_browser, mock_tools)
            )
            mock_browser_agent.return_value = mock_def

            result = await tool.execute(
                task="test task",
                purpose="testing",
            )

            # Verify BrowserAgent was created
            mock_browser_agent.assert_called_once()

            # Verify create_browser_use_agent was called
            mock_def.create_browser_use_agent.assert_called_once()

            # Verify agent.run was called
            mock_agent.run.assert_called_once_with(max_steps=50)

            # Verify browser was closed
            mock_browser.close.assert_called_once()

            assert result.success
            assert "completed" in result.output.lower()
            assert result.metadata["steps_taken"] == 2

    @pytest.mark.asyncio
    async def test_execute_passes_parameters_to_browser_agent(self):
        """Test that execute passes all parameters to BrowserAgent."""
        tool = BrowserTaskTool(headless=False)

        mock_agent = MagicMock()
        mock_history = MagicMock()
        mock_history.history = []
        mock_history.final_result = MagicMock(return_value="Done")
        mock_history.extracted_content = MagicMock(return_value=None)
        mock_agent.run = AsyncMock(return_value=mock_history)

        mock_browser = MagicMock()
        mock_browser.close = AsyncMock()

        with patch("tempo.agents.browser.BrowserAgent") as mock_browser_agent:
            mock_def = MagicMock()
            mock_def.create_browser_use_agent = MagicMock(
                return_value=(mock_agent, mock_browser, MagicMock())
            )
            mock_browser_agent.return_value = mock_def

            await tool.execute(
                task="Login to admin panel",
                url="https://example.com/login",
                scope="Only test example.com",
                use_browser_use_llm=True,
            )

            # Verify BrowserAgent was called with correct params
            call_kwargs = mock_browser_agent.call_args[1]
            assert call_kwargs["task"] == "Login to admin panel"
            assert call_kwargs["url"] == "https://example.com/login"
            assert call_kwargs["scope"] == "Only test example.com"
            assert call_kwargs["headless"] is False
            assert call_kwargs["use_browser_use_llm"] is True

    @pytest.mark.asyncio
    async def test_execute_handles_failure(self):
        """Test that execute handles browser-use agent failure."""
        tool = BrowserTaskTool()

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(side_effect=Exception("Browser crashed"))

        mock_browser = MagicMock()
        mock_browser.close = AsyncMock()

        with patch("tempo.agents.browser.BrowserAgent") as mock_browser_agent:
            mock_def = MagicMock()
            mock_def.create_browser_use_agent = MagicMock(
                return_value=(mock_agent, mock_browser, MagicMock())
            )
            mock_browser_agent.return_value = mock_def

            result = await tool.execute(task="test task")

            assert not result.success
            assert "Browser crashed" in result.error
            # Browser should still be closed on failure
            mock_browser.close.assert_called_once()
