"""Tests for PlaywrightMCPClient stdio transport."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tempo.infra.playwright_mcp import PlaywrightMCPClient, PLAYWRIGHT_MCP_TOOLS


class TestPlaywrightMCPClient:
    """Tests for PlaywrightMCPClient."""
    
    def test_init_defaults(self):
        """Test that client initializes with default values."""
        client = PlaywrightMCPClient()
        
        assert client.headless is True
        assert client.browser == "chromium"
        assert client.timeout == 60000
        assert client._process is None
        assert len(client.session_id) == 8
        
    def test_init_custom_values(self):
        """Test that client accepts custom configuration."""
        client = PlaywrightMCPClient(
            headless=False,
            browser="firefox",
            timeout=90000,
        )
        
        assert client.headless is False
        assert client.browser == "firefox"
        assert client.timeout == 90000
        
    def test_session_id_unique(self):
        """Test that each client gets a unique session ID."""
        client1 = PlaywrightMCPClient()
        client2 = PlaywrightMCPClient()
        
        assert client1.session_id != client2.session_id
        
    @pytest.mark.asyncio
    async def test_call_tool_raises_if_not_started(self):
        """Test that call_tool raises if server not started."""
        client = PlaywrightMCPClient()
        
        with pytest.raises(RuntimeError, match="not started"):
            await client.call_tool("browser_navigate", {"url": "https://example.com"})
            
    @pytest.mark.asyncio
    async def test_stop_server_terminates_process(self):
        """Test that stop_server terminates the server process."""
        client = PlaywrightMCPClient()
        
        # Simulate running server
        mock_process = AsyncMock()
        mock_process.returncode = None
        mock_process.terminate = MagicMock()
        mock_process.kill = MagicMock()
        mock_writer = AsyncMock()
        
        client._process = mock_process
        client._writer = mock_writer
        client._reader = AsyncMock()
        client._server_ready = True
        
        await client.stop_server()
        
        mock_process.terminate.assert_called_once()
        mock_writer.close.assert_called_once()
        assert client._server_ready is False
        assert client._process is None
        assert client._writer is None
        
    @pytest.mark.asyncio
    async def test_call_tool_sends_mcp_request(self):
        """Test that call_tool sends correct MCP request format."""
        client = PlaywrightMCPClient()
        client._server_ready = True
        
        # Mock reader/writer
        mock_reader = AsyncMock()
        response_json = '{"jsonrpc": "2.0", "id": "1", "result": {"content": [{"type": "text", "text": "Page loaded"}]}}'
        mock_reader.readline = AsyncMock(return_value=response_json.encode() + b"\n")
        
        mock_writer = AsyncMock()
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()
        
        client._reader = mock_reader
        client._writer = mock_writer
        
        result = await client.call_tool("browser_navigate", {"url": "https://example.com"})
        
        # Verify request was sent
        mock_writer.write.assert_called_once()
        written_data = mock_writer.write.call_args[0][0]
        
        import json
        request = json.loads(written_data.decode())
        assert request["jsonrpc"] == "2.0"
        assert request["method"] == "tools/call"
        assert request["params"]["name"] == "browser_navigate"
        assert request["params"]["arguments"]["url"] == "https://example.com"
        
        # Verify result
        assert result["success"] is True
        assert "Page loaded" in result["output"]
        
    @pytest.mark.asyncio
    async def test_call_tool_handles_error_response(self):
        """Test that call_tool handles MCP error responses."""
        client = PlaywrightMCPClient()
        client._server_ready = True
        
        # Mock reader/writer with error response
        mock_reader = AsyncMock()
        error_response = '{"jsonrpc": "2.0", "id": "1", "error": {"message": "Element not found"}}'
        mock_reader.readline = AsyncMock(return_value=error_response.encode() + b"\n")
        
        mock_writer = AsyncMock()
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()
        
        client._reader = mock_reader
        client._writer = mock_writer
        
        result = await client.call_tool("browser_click", {"element": "nonexistent"})
        
        assert result["success"] is False
        assert "Element not found" in result["error"]


class TestPlaywrightMCPTools:
    """Tests for PLAYWRIGHT_MCP_TOOLS constant."""
    
    def test_tools_defined(self):
        """Test that all expected tools are defined."""
        expected_tools = [
            "browser_navigate",
            "browser_navigate_back",
            "browser_close",
            "browser_click",
            "browser_type",
            "browser_snapshot",
            "browser_take_screenshot",
            "browser_evaluate",
            "browser_network_requests",
            "browser_console_messages",
        ]
        
        for tool in expected_tools:
            assert tool in PLAYWRIGHT_MCP_TOOLS
            
    def test_tools_have_description(self):
        """Test that all tools have descriptions."""
        for tool_name, tool_info in PLAYWRIGHT_MCP_TOOLS.items():
            assert "description" in tool_info
            assert len(tool_info["description"]) > 0
