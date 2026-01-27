"""Tests for HeadlessBrowserTool."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tempo.tools.headless_browser_tool import (
    HeadlessBrowserTool,
    ACTION_TO_MCP_TOOL,
)


class TestHeadlessBrowserTool:
    """Tests for HeadlessBrowserTool."""
    
    def test_init(self):
        """Test that tool initializes correctly."""
        tool = HeadlessBrowserTool()
        
        assert tool.name == "headless_browser"
        assert tool.category.value == "browsing"
        assert "without visual" in tool.description.lower()
        
    def test_init_with_custom_config(self):
        """Test that tool accepts custom configuration."""
        tool = HeadlessBrowserTool(
            headless=False,
            browser="firefox",
            timeout=60000,
        )
        
        assert tool._headless is False
        assert tool._browser == "firefox"
        assert tool._timeout == 60000
        
    def test_schema_includes_all_actions(self):
        """Test that schema includes all supported actions."""
        tool = HeadlessBrowserTool()
        schema = tool.get_schema()
        
        assert schema.name == "headless_browser"
        
        props = schema.parameters["properties"]
        assert "action" in props
        assert "params" in props
        assert "session_id" in props
        
        # Verify action enum contains all mapped actions
        action_enum = props["action"]["enum"]
        for action in ACTION_TO_MCP_TOOL.keys():
            assert action in action_enum
            
    def test_schema_required_fields(self):
        """Test that schema has correct required fields."""
        tool = HeadlessBrowserTool()
        schema = tool.get_schema()
        
        assert schema.parameters["required"] == ["action"]
        
    @pytest.mark.asyncio
    async def test_execute_unknown_action_returns_error(self):
        """Test that unknown action returns error result."""
        tool = HeadlessBrowserTool()
        
        result = await tool.execute(action="unknown_action")
        
        assert result.success is False
        assert "Unknown action" in result.error
        assert "available actions" in result.error.lower()
        
    @pytest.mark.asyncio
    async def test_execute_navigate_returns_session_id(self):
        """Test that navigate action returns session_id."""
        tool = HeadlessBrowserTool()
        
        mock_client = MagicMock()
        mock_client.session_id = "abc12345"
        mock_client.start_server = AsyncMock()
        mock_client.call_tool = AsyncMock(return_value={
            "success": True,
            "output": "Navigated to https://example.com",
            "raw_result": {"snapshot": "..."},
        })
        
        with patch(
            "tempo.infra.playwright_mcp.PlaywrightMCPClient",
            return_value=mock_client,
        ):
            result = await tool.execute(
                action="navigate",
                params={"url": "https://example.com"},
            )
            
        assert result.success is True
        assert result.metadata["session_id"] == "abc12345"
        assert result.metadata["action"] == "navigate"
        assert result.metadata["mcp_tool"] == "browser_navigate"
        
    @pytest.mark.asyncio
    async def test_execute_with_session_id_reuses_session(self):
        """Test that passing session_id reuses existing client."""
        tool = HeadlessBrowserTool()
        
        mock_client = MagicMock()
        mock_client.session_id = "abc12345"
        mock_client.start_server = AsyncMock()
        mock_client.call_tool = AsyncMock(return_value={
            "success": True,
            "output": "Clicked element",
        })
        
        # Pre-set the client (simulating reuse)
        tool._client = mock_client
        
        result = await tool.execute(
            action="click",
            params={"element": "submit-button"},
            session_id="abc12345",
        )
        
        # Client should not be recreated
        assert tool._client is mock_client
        assert result.success is True
        
        # Verify call_tool was called with correct params
        mock_client.call_tool.assert_called_once_with(
            "browser_click",
            {"ref": "submit-button"},
        )
        
    @pytest.mark.asyncio
    async def test_execute_normalizes_element_reference(self):
        """Test that element reference objects are normalized to strings."""
        tool = HeadlessBrowserTool()
        
        mock_client = MagicMock()
        mock_client.session_id = "abc12345"
        mock_client.start_server = AsyncMock()
        mock_client.call_tool = AsyncMock(return_value={
            "success": True,
            "output": "Clicked element",
        })
        
        with patch(
            "tempo.infra.playwright_mcp.PlaywrightMCPClient",
            return_value=mock_client,
        ):
            # Test with nested element object {"element": {"ref": "e43"}}
            await tool.execute(
                action="click",
                params={"element": {"ref": "e43"}},
            )
            
            mock_client.call_tool.assert_called_with(
                "browser_click",
                {"ref": "e43"},  # Should be normalized to string AND mapped to 'ref'
            )
            
            # Test with direct ref object {"ref": "e43"}
            await tool.execute(
                action="click",
                params={"ref": "e43"},
            )
            
            mock_client.call_tool.assert_called_with(
                "browser_click",
                {"ref": "e43"},  # Should be normalized to string AND mapped to 'ref'
            )
        
    @pytest.mark.asyncio
    async def test_execute_evaluate_js_wraps_code(self):
        """Test that evaluate_js wraps script in async function."""
        tool = HeadlessBrowserTool()
        
        mock_client = MagicMock()
        mock_client.session_id = "abc12345"
        mock_client.start_server = AsyncMock()
        mock_client.call_tool = AsyncMock(return_value={
            "success": True,
            "output": "Title",
        })
        
        with patch(
            "tempo.infra.playwright_mcp.PlaywrightMCPClient",
            return_value=mock_client,
        ):
            await tool.execute(
                action="evaluate_js",
                params={"script": "return await page.title()"},
            )
            
            mock_client.call_tool.assert_called_with(
                "browser_run_code",
                {"code": "async (page) => { return await page.evaluate(async () => { return await page.title() }) }"},
            )
        
    @pytest.mark.asyncio
    async def test_execute_handles_mcp_errors(self):
        """Test that MCP errors are handled gracefully."""
        tool = HeadlessBrowserTool()
        
        mock_client = MagicMock()
        mock_client.session_id = "abc12345"
        mock_client.start_server = AsyncMock()
        mock_client.call_tool = AsyncMock(return_value={
            "success": False,
            "error": "Element not found",
            "output": "",
        })
        
        with patch(
            "tempo.infra.playwright_mcp.PlaywrightMCPClient",
            return_value=mock_client,
        ):
            result = await tool.execute(
                action="click",
                params={"element": "nonexistent"},
            )
            
        assert result.success is False
        assert "Element not found" in result.error
        
    @pytest.mark.asyncio
    async def test_execute_handles_client_exception(self):
        """Test that client exceptions are handled."""
        tool = HeadlessBrowserTool()
        
        mock_client = MagicMock()
        mock_client.session_id = "abc12345"
        mock_client.start_server = AsyncMock()
        mock_client.call_tool = AsyncMock(side_effect=Exception("Connection failed"))
        
        with patch(
            "tempo.infra.playwright_mcp.PlaywrightMCPClient",
            return_value=mock_client,
        ):
            result = await tool.execute(
                action="navigate",
                params={"url": "https://example.com"},
            )
            
        assert result.success is False
        assert "Connection failed" in result.error
        
    @pytest.mark.asyncio
    async def test_cleanup_stops_server(self):
        """Test that cleanup stops the MCP server."""
        tool = HeadlessBrowserTool()
        
        mock_client = MagicMock()
        mock_client.stop_server = AsyncMock()
        tool._client = mock_client
        
        await tool.cleanup()
        
        mock_client.stop_server.assert_called_once()
        assert tool._client is None
        
    def test_default_summarizer_success(self):
        """Test default summarizer for successful result."""
        from tempo.tools.base import ToolResult
        
        tool = HeadlessBrowserTool()
        result = ToolResult(
            success=True,
            output="Page loaded successfully",
            metadata={"session_id": "abc12345", "action": "navigate"},
        )
        
        summary = tool.default_summarizer(result)
        
        assert "navigate" in summary
        assert "abc12345" in summary
        
    def test_default_summarizer_error(self):
        """Test default summarizer for error result."""
        from tempo.tools.base import ToolResult
        
        tool = HeadlessBrowserTool()
        result = ToolResult(
            success=False,
            output="",
            error="Element not found",
        )
        
        summary = tool.default_summarizer(result)
        
        assert "Error" in summary
        assert "Element not found" in summary


class TestActionMapping:
    """Tests for ACTION_TO_MCP_TOOL mapping."""
    
    def test_navigation_actions(self):
        """Test navigation action mappings."""
        assert ACTION_TO_MCP_TOOL["navigate"] == "browser_navigate"
        assert ACTION_TO_MCP_TOOL["go_back"] == "browser_navigate_back"
        assert ACTION_TO_MCP_TOOL["close"] == "browser_close"
        
    def test_interaction_actions(self):
        """Test interaction action mappings."""
        assert ACTION_TO_MCP_TOOL["click"] == "browser_click"
        # Type and fill_form are removed as they don't exist in Playwright MCP
        # assert ACTION_TO_MCP_TOOL["type"] == "browser_type"
        # assert ACTION_TO_MCP_TOOL["fill_form"] == "browser_fill_form"
        
    def test_state_actions(self):
        """Test state action mappings."""
        assert ACTION_TO_MCP_TOOL["snapshot"] == "browser_snapshot"
        assert ACTION_TO_MCP_TOOL["screenshot"] == "browser_take_screenshot"
        
    def test_js_actions(self):
        """Test JavaScript action mappings."""
        assert ACTION_TO_MCP_TOOL["evaluate_js"] == "browser_run_code"
        
    def test_introspection_actions(self):
        """Test introspection action mappings."""
        assert ACTION_TO_MCP_TOOL["get_network_requests"] == "browser_network_requests"
        # browser_console_messages removed
        # assert ACTION_TO_MCP_TOOL["get_console_messages"] == "browser_console_messages"
